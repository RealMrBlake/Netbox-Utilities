from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied

from netbox_utilities.reorder_rack import (
    RackLayoutError,
    apply_rack_layout,
    bulk_reorder_update,
    install_reorder_rack_bulk_save,
    parse_device_placements,
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
            [(item.device_id, item.position, item.face) for item in placements],
            [
                (10, Decimal(4), "front"),
                (11, Decimal("8.5"), "front"),
                (12, None, ""),
            ],
        )

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
    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    def test_clears_all_old_positions_before_saving_targets(self, device_model, _get_permission):
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

    @patch("netbox_utilities.reorder_rack.get_permission_for_model", return_value="dcim.change_device")
    @patch("netbox_utilities.reorder_rack.Device")
    def test_rejects_changed_device_without_permission(self, device_model, _get_permission):
        device = MagicMock(pk=10, position=Decimal(1), face="front")
        device_model.objects.select_for_update.return_value.filter.return_value = [device]
        user = MagicMock()
        user.has_perm.return_value = False
        placements = parse_device_placements(rack_layout(front=[{"id": 10, "y": 2}]))

        with self.assertRaises(PermissionDenied):
            apply_rack_layout(rack=SimpleNamespace(pk=5), placements=placements, user=user)

        device_model.objects.filter.assert_not_called()
        device.save.assert_not_called()


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
