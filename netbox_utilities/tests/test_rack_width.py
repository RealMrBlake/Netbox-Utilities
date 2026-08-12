from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from netbox_utilities.rack_width import (
    _cleanup_unracked_placement,
    available_units_for_device,
    horizontal_interval,
    intervals_cover_full_width,
    intervals_overlap,
    normalize_width_position,
    placement_rectangles_overlap,
    stage_width_position,
)


class RackWidthTest(SimpleTestCase):
    def test_device_edit_view_uses_explicit_rack_width_form(self):
        from dcim.views import DeviceEditView

        self.assertEqual(DeviceEditView.form.__name__, "RackWidthDeviceForm")
        self.assertIn("utilities_rack_width", DeviceEditView.form.base_fields)
        self.assertIn("utilities_horizontal_position", DeviceEditView.form.base_fields)

    def test_normalizes_full_width_to_first_position(self):
        self.assertEqual(normalize_width_position(1, 4), (1, 1))

    def test_rejects_position_outside_selected_width(self):
        with self.assertRaises(ValidationError):
            normalize_width_position(2, 3)

    def test_adjacent_half_widths_do_not_overlap(self):
        self.assertFalse(intervals_overlap(horizontal_interval(2, 1), horizontal_interval(2, 2)))

    def test_half_width_overlaps_full_width(self):
        self.assertTrue(intervals_overlap(horizontal_interval(1, 1), horizontal_interval(2, 2)))

    def test_two_halves_cover_full_width(self):
        self.assertTrue(intervals_cover_full_width([horizontal_interval(2, 1), horizontal_interval(2, 2)]))

    def test_single_half_does_not_cover_full_width(self):
        self.assertFalse(intervals_cover_full_width([horizontal_interval(2, 1)]))

    def test_same_unit_adjacent_devices_do_not_collide(self):
        self.assertFalse(placement_rectangles_overlap(10, 1, 2, 1, 10, 1, 2, 2))

    def test_multi_unit_device_collides_only_on_same_horizontal_area(self):
        self.assertTrue(placement_rectangles_overlap(10, 2, 2, 1, 11, 1, 2, 1))
        self.assertFalse(placement_rectangles_overlap(10, 2, 2, 1, 11, 1, 2, 2))

    def test_stages_width_without_requiring_an_already_assigned_rack(self):
        device = SimpleNamespace()

        stage_width_position(device, 2, 2)

        self.assertEqual(device._netbox_utilities_rack_width, 2)
        self.assertEqual(device._netbox_utilities_horizontal_position, 2)

    @patch("netbox_utilities.rack_width.find_placement_conflict", return_value=None)
    def test_current_position_is_available_without_conflict(self, _find_conflict):
        rack = SimpleNamespace(units=[1, 1.5, 2, 2.5])
        device = SimpleNamespace(
            position=1,
            device_type=SimpleNamespace(u_height=1),
        )

        self.assertEqual(available_units_for_device(rack, device), [1])

    @patch("netbox_utilities.rack_width.DeviceRackPlacement.objects")
    def test_unracked_device_removes_stale_width(self, placement_objects):
        device = SimpleNamespace(pk=12, rack_id=None, position=None)

        _cleanup_unracked_placement(None, device, using="default")

        placement_objects.using.assert_called_once_with("default")
        placement_objects.using.return_value.filter.assert_called_once_with(device_id=12)
        placement_objects.using.return_value.filter.return_value.delete.assert_called_once_with()


class RackWidthMigrationTest(SimpleTestCase):
    def test_postgresql_migration_drops_core_uniqueness(self):
        migration = import_module("netbox_utilities.migrations.0007_devicerackplacement")
        schema_editor = SimpleNamespace(
            connection=SimpleNamespace(vendor="postgresql"),
            execute=MagicMock(),
        )

        migration.drop_core_rack_position_constraint(None, schema_editor)

        statement = schema_editor.execute.call_args.args[0]
        self.assertIn("DROP CONSTRAINT IF EXISTS", statement)
        self.assertIn("dcim_device_unique_rack_position_face", statement)
