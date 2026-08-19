from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.template.loader import get_template, render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse
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
    width_aware_reorder_get,
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
        first = MagicMock(
            pk=10,
            rack_id=5,
            position=Decimal(1),
            face="front",
            device_type=SimpleNamespace(u_height=1),
        )
        second = MagicMock(
            pk=11,
            rack_id=5,
            position=Decimal(2),
            face="front",
            device_type=SimpleNamespace(u_height=1),
        )
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
        device = MagicMock(
            pk=10,
            rack_id=5,
            position=Decimal(1),
            face="front",
            device_type=SimpleNamespace(u_height=1),
        )
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
        device = MagicMock(
            pk=10,
            rack_id=5,
            position=Decimal(4),
            face="front",
            device_type=SimpleNamespace(u_height=1),
        )
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
        device = MagicMock(
            pk=10,
            rack_id=5,
            position=Decimal(4),
            face="front",
            device_type=SimpleNamespace(u_height=1),
        )
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

    @patch("netbox_utilities.reorder_rack.DeviceRackPlacement")
    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    def test_persists_inferred_half_width_when_shared_device_is_moved(
        self,
        device_model,
        _get_permission,
        placement_model,
    ):
        left = MagicMock(
            pk=10,
            rack_id=5,
            position=Decimal(4),
            face="front",
            device_type=SimpleNamespace(u_height=1),
        )
        right = MagicMock(
            pk=11,
            rack_id=5,
            position=Decimal(4),
            face="front",
            device_type=SimpleNamespace(u_height=1),
        )
        device_model.objects.select_for_update.return_value.filter.return_value = [left, right]
        placement_model.objects.select_for_update.return_value.filter.return_value = []
        user = MagicMock()
        user.has_perm.return_value = True
        placements = parse_device_placements(
            rack_layout(
                front=[
                    {"id": 10, "x": 0, "y": 4},
                    {"id": 11, "x": 6, "y": 5},
                ]
            ),
            grid_columns=12,
        )

        changed = apply_rack_layout(rack=SimpleNamespace(pk=5), placements=placements, user=user)

        self.assertEqual(changed, [right])
        placement_model.objects.update_or_create.assert_called_once_with(
            device=right,
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
        self.assertIn("if (face !== 'other')", script)
        self.assertIn("data.schema_version !== 3", script)
        self.assertIn("data.complete !== true", script)
        self.assertIn("nativeMountedItems.length", script)
        self.assertIn("const nativeItemsByFace = {}", script)
        self.assertIn("const device = devicesById.get", script)
        self.assertIn("if (!nativeItemsByFace[face].has", script)
        self.assertNotIn("partialDeviceIds", script)
        self.assertNotIn("JSON.stringify", script)

    def test_server_template_uses_complete_twelve_column_device_payload(self):
        templates = Path(__file__).parents[1] / "templates" / "netbox_utilities"
        page = (templates / "reorder_rack.html").read_text(encoding="utf-8")
        grid = (templates / "reorder_rack_grid.html").read_text(encoding="utf-8")

        self.assertIn('include "netbox_utilities/reorder_rack_grid.html"', page)
        self.assertIn('gs-column="12"', grid)
        self.assertIn("{% for device in reorder_devices %}", grid)
        self.assertIn('gs-w="{{ device.grid_width }}"', grid)
        self.assertIn('gs-x="{{ device.grid_x }}"', grid)
        self.assertIn("netbox-utilities-reorder-grid", grid)
        self.assertIn('json_script:"netbox-utilities-reorder-rack-width-data"', page)
        self.assertIn("netbox_utilities/reorder-rack-width.js", page)

        get_template("netbox_utilities/reorder_rack.html")
        rendered_grid = render_to_string(
            "netbox_utilities/reorder_rack_grid.html",
            {
                "object": SimpleNamespace(units=[1], u_height=42),
                "face": "front",
                "grid_id": 0,
                "reorder_devices": [
                    {
                        "id": 10,
                        "label": "LEO-Fritzbox",
                        "face": "front",
                        "full_depth": False,
                        "grid_x": 0,
                        "grid_y": 62,
                        "grid_width": 6,
                        "grid_height": 2,
                        "width": 2,
                        "horizontal_position": 1,
                        "color": "f0a000",
                        "text_color": "000000",
                        "locked": False,
                    }
                ],
            },
        )
        self.assertIn('gs-column="12"', rendered_grid)
        self.assertIn('gs-id="10"', rendered_grid)
        self.assertIn("LEO-Fritzbox", rendered_grid)

        stylesheet = (Path(__file__).parents[1] / "static" / "netbox_utilities" / "netbox_utilities.css").read_text(
            encoding="utf-8"
        )
        self.assertIn('.netbox-utilities-reorder-grid[gs-column="12"]', stylesheet)
        self.assertIn('.grid-stack-item[gs-w="6"] { width: 50%; }', stylesheet)
        self.assertIn('.grid-stack-item[gs-w="12"] { width: 100%; }', stylesheet)
        self.assertIn('.grid-stack-item[gs-x="6"] { left: 50%; }', stylesheet)
        self.assertNotIn('.grid-stack-item[gs-w="6"] { width: 50% !important; }', stylesheet)

        rendered_image_grid = render_to_string(
            "netbox_utilities/reorder_rack_grid.html",
            {
                "object": SimpleNamespace(units=[1], u_height=42),
                "face": "front",
                "grid_id": 0,
                "images": True,
                "labels": False,
                "unit_width": 220,
                "reorder_devices": [
                    {
                        "id": 10,
                        "label": "LEO-Fritzbox",
                        "face": "front",
                        "full_depth": False,
                        "grid_x": 0,
                        "grid_y": 62,
                        "grid_width": 6,
                        "grid_height": 2,
                        "width": 2,
                        "horizontal_position": 1,
                        "color": "f0a000",
                        "text_color": "000000",
                        "locked": False,
                        "front_image": "/media/device-type-images/fritzbox.png",
                        "rear_image": None,
                    }
                ],
            },
        )
        self.assertIn("background-image: url('/media/device-type-images/fritzbox.png')", rendered_image_grid)
        self.assertIn("background-size: 220px", rendered_image_grid)
        self.assertNotIn(">LEO-Fritzbox<", rendered_image_grid.replace("\n", ""))

    def test_resolved_reorder_page_uses_server_side_width_view(self):
        view_class = resolve(reverse("dcim:rack_reorder", kwargs={"pk": 3})).func.view_class

        self.assertIs(view_class.get, width_aware_reorder_get)
        self.assertEqual(view_class.get.__module__, "netbox_utilities.reorder_rack")

    @patch("netbox_utilities.reorder_rack.get_reorder_rack_width_data")
    @patch("netbox_utilities.reorder_rack.get_object_or_404")
    @patch("netbox_utilities.reorder_rack.Device")
    @patch("django.shortcuts.render")
    def test_server_side_reorder_view_renders_payload_devices(
        self,
        render_mock,
        device_model,
        get_object,
        get_width_data,
    ):
        from dcim.models import Rack, Site

        rack = Rack(
            pk=3,
            name="Rack02 - Rechts",
            site=Site(pk=1, name="AWO-MWT Leonardo Schule", slug="leonardo"),
            u_height=42,
        )
        get_object.return_value = rack
        device_model.objects.filter.return_value.exclude.return_value.select_related.return_value = []
        get_width_data.return_value = {
            "complete": True,
            "unit_width": 220,
            "devices": [
                {
                    "id": 10,
                    "label": "LEO-Fritzbox",
                    "face": "front",
                    "full_depth": False,
                    "grid_x": 0,
                    "grid_y": 62,
                    "grid_width": 6,
                    "grid_height": 2,
                    "width": 2,
                    "horizontal_position": 1,
                    "color": "f0a000",
                    "text_color": "000000",
                    "locked": False,
                }
            ],
        }
        request = RequestFactory().get("/dcim/racks/3/reorder/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        expected_response = SimpleNamespace(status_code=200)
        render_mock.return_value = expected_response

        response = width_aware_reorder_get(SimpleNamespace(), request, 3)

        self.assertIs(response, expected_response)
        template_name = render_mock.call_args.args[1]
        context = render_mock.call_args.args[2]
        self.assertEqual(template_name, "netbox_utilities/reorder_rack.html")
        self.assertEqual(context["reorder_devices"][0]["label"], "LEO-Fritzbox")
        self.assertEqual(context["reorder_devices"][0]["grid_width"], 6)
        self.assertEqual(context["asset_version"], "0.9.10")
        self.assertIs(context["reorder_rack_width_data"], get_width_data.return_value)
        get_width_data.assert_called_once()
        self.assertIs(get_width_data.call_args.kwargs["rack"], rack)
        self.assertIsNotNone(get_width_data.call_args.kwargs["devices"])

    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    def test_view_owned_rack_data_does_not_repeat_route_or_object_filtering(self, _get_permission):
        request = RequestFactory().get("/dcim/racks/3/reorder/")
        request.user = MagicMock()
        request.user.has_perm.return_value = True
        rack = SimpleNamespace(pk=3, u_height=42, desc_units=False)
        device = SimpleNamespace(
            pk=334,
            rack_id=3,
            label="LEO-Fritzbox",
            device_type=SimpleNamespace(
                u_height=1,
                is_full_depth=False,
                front_image=None,
                rear_image=None,
            ),
            role=SimpleNamespace(color="f0a000"),
            face="front",
            position=Decimal(11),
            netbox_utilities_rack_placement=SimpleNamespace(width=2, horizontal_position=1),
        )

        with (
            patch("netbox_utilities.reorder_rack.reorder_rack_width_enabled") as enabled,
            patch("netbox.config.get_config", return_value=SimpleNamespace(RACK_ELEVATION_DEFAULT_UNIT_WIDTH=220)),
            patch("utilities.html.foreground_color", return_value="000000"),
        ):
            result = get_reorder_rack_width_data(request, rack=rack, devices=[device])

        enabled.assert_not_called()
        self.assertTrue(result["complete"])
        self.assertEqual(result["devices"][0]["id"], 334)
        self.assertEqual(result["devices"][0]["grid_width"], 6)

    @patch("netbox_utilities.reorder_rack.reorder_rack_width_enabled", return_value=True)
    @patch("netbox_utilities.reorder_rack.Rack")
    def test_malformed_partial_placement_fails_open(self, rack_model, _enabled):
        request = RequestFactory().get("/dcim/racks/5/reorder/")
        request.resolver_match = SimpleNamespace(kwargs={"pk": 5}, view_name="dcim:rack_reorder")
        request.user = MagicMock()
        rack_model.objects.restrict.return_value.filter.return_value.first.return_value = SimpleNamespace(pk=5)

        with patch("netbox_utilities.reorder_rack.Device.objects.restrict", side_effect=AttributeError("stale")):
            result = get_reorder_rack_width_data(request)

        self.assertEqual(result["status"], "native-fallback")
        self.assertEqual(result["devices"], [])
        self.assertFalse(result["complete"])

    @patch("netbox_utilities.reorder_rack.reorder_rack_width_enabled", return_value=True)
    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    @patch("netbox_utilities.reorder_rack.Rack")
    def test_describes_every_mounted_device_for_reorder_grid(
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
            rack_id=5,
            name="Fritzbox",
            label="Fritzbox",
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
        adjacent_device = SimpleNamespace(
            pk=12,
            rack_id=5,
            name="Router",
            label="Router",
            virtual_chassis=None,
            device_type=SimpleNamespace(
                u_height=1,
                is_full_depth=False,
                front_image=None,
                rear_image=None,
            ),
            role=SimpleNamespace(color="fedcba"),
            face="front",
            position=Decimal(4),
            netbox_utilities_rack_placement=SimpleNamespace(width=2, horizontal_position=1),
        )
        full_width_device = SimpleNamespace(
            pk=11,
            rack_id=5,
            name="Switch",
            label="Switch",
            virtual_chassis=None,
            device_type=SimpleNamespace(
                u_height=1,
                is_full_depth=False,
                front_image=None,
                rear_image=None,
            ),
            role=SimpleNamespace(color="123456"),
            face="front",
            position=Decimal(5),
            netbox_utilities_rack_placement=None,
        )
        device_queryset = MagicMock()
        device_queryset.filter.return_value.select_related.return_value.order_by.return_value = [
            device,
            adjacent_device,
            full_width_device,
        ]
        device_model.objects.restrict.return_value = device_queryset

        with (
            patch(
                "netbox.config.get_config",
                return_value=SimpleNamespace(RACK_ELEVATION_DEFAULT_UNIT_WIDTH=220),
            ),
            patch("utilities.html.foreground_color", return_value="000000"),
        ):
            result = get_reorder_rack_width_data(request)

        self.assertEqual(result["columns"], 12)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["schema_version"], 3)
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["devices"]), 3)
        self.assertEqual(result["devices"][0]["label"], "Fritzbox")
        self.assertFalse(result["images"])
        self.assertTrue(result["labels"])
        device_queryset.filter.assert_called_once_with(
            rack=rack,
            position__gt=0,
            device_type__u_height__gt=0,
        )
        self.assertEqual(
            {key: result["devices"][0][key] for key in ("id", "grid_x", "grid_width", "width", "horizontal_position")},
            {"id": 10, "grid_x": 6, "grid_width": 6, "width": 2, "horizontal_position": 2},
        )
        self.assertEqual(
            {key: result["devices"][1][key] for key in ("id", "grid_x", "grid_width", "width")},
            {"id": 12, "grid_x": 0, "grid_width": 6, "width": 2},
        )
        self.assertEqual(
            {key: result["devices"][2][key] for key in ("id", "grid_x", "grid_width", "width")},
            {"id": 11, "grid_x": 0, "grid_width": 12, "width": 1},
        )
        self.assertEqual(
            [device["width_source"] for device in result["devices"]],
            ["stored", "stored", "default"],
        )


class ReorderRackPatchTest(SimpleTestCase):
    def test_patches_supported_plugin_only_once(self):
        original_update = object()

        def original_get(self, request, pk):
            return self, request, pk

        class SaveViewSet:
            update = original_update

        class ReorderView:
            get = original_get

        api_views = SimpleNamespace(SaveViewSet=SaveViewSet)
        page_views = SimpleNamespace(ReorderView=ReorderView)
        plugin_config = SimpleNamespace(version="1.1.4")

        with (
            patch("netbox_utilities.reorder_rack.apps.is_installed", return_value=True),
            patch("netbox_utilities.reorder_rack.apps.get_app_config", return_value=plugin_config),
            patch(
                "netbox_utilities.reorder_rack.import_module",
                side_effect=lambda name: api_views if name.endswith("api.views") else page_views,
            ),
        ):
            self.assertTrue(install_reorder_rack_bulk_save())
            self.assertTrue(install_reorder_rack_bulk_save())

        self.assertIs(SaveViewSet.update, bulk_reorder_update)
        self.assertIs(SaveViewSet._netbox_utilities_original_update, original_update)
        self.assertIs(ReorderView.get, width_aware_reorder_get)
        self.assertIs(ReorderView._netbox_utilities_original_get, original_get)

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
