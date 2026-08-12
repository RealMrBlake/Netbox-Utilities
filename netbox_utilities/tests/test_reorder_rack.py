from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase
from rest_framework.exceptions import PermissionDenied

from netbox_utilities.reorder_rack import (
    RackLayoutError,
    apply_rack_layout,
    bulk_reorder_update,
    get_reorder_rack_width_data,
    grid_dimensions,
    horizontal_position_from_grid_x,
    install_reorder_rack_bulk_save,
    parse_device_placements,
    reorder_grid_y,
)


def rack_layout(front=None, rear=None, other=None):
    return {
        "front": front or [],
        "rear": rear or [],
        "other": other or [],
    }


class RackLayoutParsingTest(SimpleTestCase):
    def test_parses_multiple_device_positions(self):
        placements = parse_device_placements(
            rack_layout(
                front=[{"id": 10, "y": 4}, {"id": 11, "y": 8.5}],
                other=[{"id": 12, "y": None}],
            )
        )

        self.assertEqual(
            [(item.device_id, item.position, item.face, item.grid_x) for item in placements],
            [
                (10, Decimal(4), "front", None),
                (11, Decimal("8.5"), "front", None),
                (12, None, "", None),
            ],
        )

    def test_reads_horizontal_positions_only_from_marked_twelve_column_payload(self):
        placements = parse_device_placements(
            rack_layout(front=[{"id": 10, "x": 6, "y": 4}]),
            grid_columns=12,
        )

        self.assertEqual(placements[0].grid_x, 6)

    def test_maps_rack_widths_to_twelve_column_grid(self):
        self.assertEqual(grid_dimensions(1, 1), (12, 0))
        self.assertEqual(grid_dimensions(2, 2), (6, 6))
        self.assertEqual(grid_dimensions(3, 2), (4, 4))
        self.assertEqual(grid_dimensions(4, 4), (3, 9))

    def test_maps_grid_x_back_to_horizontal_position(self):
        self.assertEqual(horizontal_position_from_grid_x(2, 6), 2)
        self.assertEqual(horizontal_position_from_grid_x(3, 8), 3)
        self.assertEqual(horizontal_position_from_grid_x(4, 9), 4)

    def test_rejects_misaligned_grid_position(self):
        with self.assertRaisesMessage(RackLayoutError, "nicht zulässig"):
            horizontal_position_from_grid_x(2, 3)

    def test_rejects_non_integer_grid_position(self):
        with self.assertRaisesMessage(RackLayoutError, "ganze Zahl"):
            horizontal_position_from_grid_x(2, 6.0)

    def test_rejects_duplicate_devices(self):
        with self.assertRaisesMessage(RackLayoutError, "mehrfach"):
            parse_device_placements(
                rack_layout(
                    front=[{"id": 10, "y": 4}],
                    rear=[{"id": 10, "y": 6}],
                )
            )

    def test_rejects_invalid_positions(self):
        with self.assertRaisesMessage(RackLayoutError, "keine gültige Rack-Position"):
            parse_device_placements(rack_layout(front=[{"id": 10, "y": "not-a-position"}]))


class ApplyRackLayoutTest(SimpleTestCase):
    @patch("netbox_utilities.reorder_rack.DeviceRackPlacement")
    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    def test_clears_all_old_positions_before_saving_targets(
        self,
        device_model,
        _get_permission,
        placement_model,
    ):
        events = []
        first = MagicMock(pk=10, position=Decimal(1), face="front")
        second = MagicMock(pk=11, position=Decimal(2), face="front")
        first.snapshot.side_effect = lambda: events.append("snapshot-10")
        second.snapshot.side_effect = lambda: events.append("snapshot-11")
        first.full_clean.side_effect = lambda: events.append("validate-10")
        second.full_clean.side_effect = lambda: events.append("validate-11")
        first.save.side_effect = lambda: events.append("save-10")
        second.save.side_effect = lambda: events.append("save-11")

        device_model.objects.select_for_update.return_value.filter.return_value = [first, second]
        device_model.objects.filter.return_value.update.side_effect = lambda **_kwargs: events.append("clear")
        placement_model.objects.select_for_update.return_value.filter.return_value = []
        user = MagicMock()
        user.has_perm.return_value = True
        placements = parse_device_placements(rack_layout(front=[{"id": 10, "y": 2}, {"id": 11, "y": 1}]))

        changed = apply_rack_layout(rack=SimpleNamespace(pk=5), placements=placements, user=user)

        self.assertEqual(changed, [first, second])
        self.assertLess(events.index("clear"), events.index("validate-10"))
        self.assertLess(events.index("clear"), events.index("validate-11"))
        device_model.objects.filter.return_value.update.assert_called_once_with(position=None, face="")
        self.assertEqual((first.position, first.face), (Decimal(2), "front"))
        self.assertEqual((second.position, second.face), (Decimal(1), "front"))

    @patch("netbox_utilities.reorder_rack.DeviceRackPlacement")
    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    def test_rejects_changed_device_without_permission(self, device_model, _get_permission, placement_model):
        device = MagicMock(pk=10, position=Decimal(1), face="front")
        device_model.objects.select_for_update.return_value.filter.return_value = [device]
        placement_model.objects.select_for_update.return_value.filter.return_value = []
        user = MagicMock()
        user.has_perm.return_value = False
        placements = parse_device_placements(rack_layout(front=[{"id": 10, "y": 2}]))

        with self.assertRaises(PermissionDenied):
            apply_rack_layout(rack=SimpleNamespace(pk=5), placements=placements, user=user)

        device_model.objects.filter.assert_not_called()
        device.save.assert_not_called()

    @patch("netbox_utilities.reorder_rack.DeviceRackPlacement")
    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    def test_saves_horizontal_only_move_for_partial_width_device(
        self,
        device_model,
        _get_permission,
        placement_model,
    ):
        device = MagicMock(pk=10, position=Decimal(4), face="front")
        stored = SimpleNamespace(device_id=10, width=2, horizontal_position=1)
        device_model.objects.select_for_update.return_value.filter.return_value = [device]
        placement_model.objects.select_for_update.return_value.filter.return_value = [stored]
        user = MagicMock()
        user.has_perm.return_value = True
        placements = parse_device_placements(
            rack_layout(front=[{"id": 10, "x": 6, "y": 4}]),
            grid_columns=12,
        )

        changed = apply_rack_layout(rack=SimpleNamespace(pk=5), placements=placements, user=user)

        self.assertEqual(changed, [device])
        self.assertEqual(device._netbox_utilities_rack_width, 2)
        self.assertEqual(device._netbox_utilities_horizontal_position, 2)
        placement_model.objects.update_or_create.assert_called_once_with(
            device=device,
            defaults={"width": 2, "horizontal_position": 2},
        )

    @patch("netbox_utilities.reorder_rack.DeviceRackPlacement")
    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    def test_legacy_payload_preserves_stored_horizontal_position(
        self,
        device_model,
        _get_permission,
        placement_model,
    ):
        device = MagicMock(pk=10, position=Decimal(4), face="front")
        stored = SimpleNamespace(device_id=10, width=2, horizontal_position=2)
        device_model.objects.select_for_update.return_value.filter.return_value = [device]
        placement_model.objects.select_for_update.return_value.filter.return_value = [stored]
        user = MagicMock()
        user.has_perm.return_value = True
        placements = parse_device_placements(rack_layout(front=[{"id": 10, "x": 0, "y": 5}]))

        changed = apply_rack_layout(rack=SimpleNamespace(pk=5), placements=placements, user=user)

        self.assertEqual(changed, [device])
        placement_model.objects.update_or_create.assert_called_once_with(
            device=device,
            defaults={"width": 2, "horizontal_position": 2},
        )


class ReorderRackFrontendTest(SimpleTestCase):
    def test_grid_y_matches_reorder_plugin_for_both_numbering_directions(self):
        self.assertEqual(reorder_grid_y(SimpleNamespace(u_height=42, desc_units=True), 4, 2), 6)
        self.assertEqual(reorder_grid_y(SimpleNamespace(u_height=42, desc_units=False), 4, 2), 74)

    def test_width_adapter_runs_before_gridstack_and_preserves_original_save(self):
        script = (Path(__file__).parents[1] / "static" / "netbox_utilities" / "reorder-rack-width.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("setAttribute(grid, 'gs-column', columns)", script)
        self.assertIn("setAttribute(item, 'gs-w', device.grid_width)", script)
        self.assertIn("setAttribute(item, 'gs-x', device.grid_x)", script)
        self.assertIn("grid.on('dragstop'", script)
        self.assertIn("grid.on('dropped'", script)
        self.assertIn("closest('#saveButton')", script)
        self.assertIn("X-NetBox-Utilities-Rack-Grid-Columns", script)
        self.assertNotIn("JSON.stringify", script)

    @patch("netbox_utilities.reorder_rack.reorder_rack_width_enabled", return_value=True)
    @patch("netbox_utilities.reorder_rack.Rack")
    def test_malformed_partial_placement_fails_open(self, rack_model, _enabled):
        request = RequestFactory().get("/dcim/racks/5/reorder/")
        request.resolver_match = SimpleNamespace(kwargs={"pk": 5}, view_name="dcim:rack_reorder")
        request.user = MagicMock()
        rack_model.objects.restrict.return_value.filter.return_value.first.return_value = SimpleNamespace(pk=5)

        with patch("netbox_utilities.reorder_rack.Device.objects.restrict", side_effect=AttributeError("stale")):
            self.assertIsNone(get_reorder_rack_width_data(request))

    @patch("netbox_utilities.reorder_rack.reorder_rack_width_enabled", return_value=True)
    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    @patch("netbox_utilities.reorder_rack.Rack")
    def test_describes_partial_devices_for_reorder_grid(
        self,
        rack_model,
        device_model,
        _get_permission,
        _enabled,
    ):
        request = RequestFactory().get("/dcim/racks/5/reorder/?view=labels-only")
        request.resolver_match = SimpleNamespace(kwargs={"pk": 5}, view_name="dcim:rack_reorder")
        request.user = MagicMock()
        request.user.has_perm.return_value = True
        rack = SimpleNamespace(pk=5, u_height=42, desc_units=False)
        rack_model.objects.restrict.return_value.filter.return_value.first.return_value = rack
        placement = SimpleNamespace(width=2, horizontal_position=2)
        device = SimpleNamespace(
            pk=10,
            name="Fritzbox",
            virtual_chassis=None,
            device_type=SimpleNamespace(
                u_height=1,
                is_full_depth=False,
                front_image=None,
                rear_image=None,
            ),
            role=SimpleNamespace(color="abcdef"),
            face="front",
            position=Decimal(4),
            netbox_utilities_rack_placement=placement,
        )
        device_queryset = MagicMock()
        device_queryset.filter.return_value.select_related.return_value.order_by.return_value = [device]
        device_model.objects.restrict.return_value = device_queryset

        with (
            patch("dcim.svg.racks.get_device_name", return_value="Fritzbox"),
            patch(
                "netbox.config.get_config",
                return_value=SimpleNamespace(RACK_ELEVATION_DEFAULT_UNIT_WIDTH=220),
            ),
            patch("utilities.html.foreground_color", return_value="000000"),
        ):
            result = get_reorder_rack_width_data(request)

        self.assertEqual(result["columns"], 12)
        self.assertFalse(result["images"])
        self.assertTrue(result["labels"])
        self.assertEqual(
            {key: result["devices"][0][key] for key in ("id", "grid_x", "grid_width", "width", "horizontal_position")},
            {"id": 10, "grid_x": 6, "grid_width": 6, "width": 2, "horizontal_position": 2},
        )


class ReorderRackPatchTest(SimpleTestCase):
    def test_patches_supported_plugin_only_once(self):
        original_update = object()

        class SaveViewSet:
            update = original_update

        views = SimpleNamespace(SaveViewSet=SaveViewSet)
        plugin_config = SimpleNamespace(version="1.1.4")

        with (
            patch("netbox_utilities.reorder_rack.apps.is_installed", return_value=True),
            patch("netbox_utilities.reorder_rack.apps.get_app_config", return_value=plugin_config),
            patch("netbox_utilities.reorder_rack.import_module", return_value=views),
        ):
            self.assertTrue(install_reorder_rack_bulk_save())
            self.assertTrue(install_reorder_rack_bulk_save())

        self.assertIs(SaveViewSet.update, bulk_reorder_update)
        self.assertIs(SaveViewSet._netbox_utilities_original_update, original_update)

    def test_skips_unsupported_plugin_version(self):
        with (
            patch("netbox_utilities.reorder_rack.apps.is_installed", return_value=True),
            patch(
                "netbox_utilities.reorder_rack.apps.get_app_config",
                return_value=SimpleNamespace(version="2.0.0"),
            ),
            patch("netbox_utilities.reorder_rack.import_module") as import_module_mock,
        ):
            self.assertFalse(install_reorder_rack_bulk_save())

        import_module_mock.assert_not_called()
