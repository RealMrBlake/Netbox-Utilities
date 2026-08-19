from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from netbox_utilities.netbox_export import (
    PATCH_MARKER,
    PATCH_VERSION,
    RACK_WIDTH_RECORD_KEY,
    WidthAwareDeferredDevicePlacement,
    _apply_rack_widths,
    _defer_rack_width,
    _serialize_rack_width,
    _width_aware_device_placement_conflicts,
    install_netbox_export_rack_width_support,
)


class FakeQuerySet(list):
    def __init__(self, values=()):
        super().__init__(values)
        self.selected_related = []

    def select_for_update(self):
        return self

    def select_related(self, *args):
        self.selected_related.append(args)
        return self

    def filter(self, **kwargs):
        return self

    def exclude(self, **kwargs):
        pk = kwargs.get("pk")
        result = FakeQuerySet(item for item in self if item.pk != pk)
        result.selected_related = self.selected_related
        return result


class FakeDevice:
    _meta = SimpleNamespace(label_lower="dcim.device")
    _default_manager = FakeQuerySet()

    def __init__(self, pk, *, width=1, horizontal_position=1, position=None, face="front", full_depth=False):
        self.pk = pk
        self.rack_id = 1 if position is not None else None
        self.position = position
        self.face = face
        self.device_type = SimpleNamespace(u_height=1, is_full_depth=full_depth)
        if width != 1:
            self.netbox_utilities_rack_placement = SimpleNamespace(
                width=width,
                horizontal_position=horizontal_position,
            )


class NetBoxExportRackWidthTest(SimpleTestCase):
    def test_export_embeds_partial_and_full_rack_widths_on_devices(self):
        partial = FakeDevice(1, width=2, horizontal_position=2)
        full = FakeDevice(2)
        original = lambda obj, *args, **kwargs: {"id": f"dcim.device:{obj.pk}"}

        partial_record = _serialize_rack_width(original, partial)
        full_record = _serialize_rack_width(original, full)

        self.assertEqual(
            partial_record[RACK_WIDTH_RECORD_KEY],
            {"schema_version": 1, "width": 2, "horizontal_position": 2},
        )
        self.assertEqual(
            full_record[RACK_WIDTH_RECORD_KEY],
            {"schema_version": 1, "width": 1, "horizontal_position": 1},
        )

    def test_import_reads_width_metadata_without_breaking_legacy_archives(self):
        native = SimpleNamespace(rack_spec={"ref": "dcim.rack:2"}, position=11, face="front")
        original = MagicMock(return_value=({"fields": {}}, native))
        record = {
            "id": "dcim.device:334",
            RACK_WIDTH_RECORD_KEY: {
                "schema_version": 1,
                "width": 2,
                "horizontal_position": 2,
            },
        }

        prepared, placement = _defer_rack_width(original, FakeDevice, record)

        self.assertEqual(prepared, {"fields": {}})
        self.assertEqual(
            placement,
            WidthAwareDeferredDevicePlacement(
                rack_spec={"ref": "dcim.rack:2"},
                position=11,
                face="front",
                width=2,
                horizontal_position=2,
            ),
        )

        legacy_record = {"id": "dcim.device:334"}
        self.assertIs(_defer_rack_width(original, FakeDevice, legacy_record)[1], native)

    @patch("netbox_utilities.netbox_export.normalize_width_position", side_effect=ValidationError("invalid"))
    def test_invalid_width_metadata_falls_back_to_native_import(self, _normalize):
        native = SimpleNamespace(rack_spec=None, position=11, face="front")
        original = MagicMock(return_value=({}, native))
        record = {
            "id": "dcim.device:334",
            RACK_WIDTH_RECORD_KEY: {
                "schema_version": 1,
                "width": 9,
                "horizontal_position": 9,
            },
        }

        self.assertIs(_defer_rack_width(original, FakeDevice, record)[1], native)

    @patch("netbox_utilities.netbox_export.DeviceRackPlacement.objects")
    def test_import_conflicts_respect_horizontal_rack_positions(self, placement_objects):
        left = FakeDevice(1, width=2, horizontal_position=1, position=11)
        right = FakeDevice(2, width=2, horizontal_position=2)
        right.rack_id = 1
        FakeDevice._default_manager = FakeQuerySet([left])
        stored_left = SimpleNamespace(device_id=1, width=2, horizontal_position=1)
        placement_objects.select_for_update.return_value.filter.return_value = [stored_left]
        original = MagicMock()

        conflicts = _width_aware_device_placement_conflicts(original, right, object(), 11, "front")

        self.assertEqual(conflicts, [])
        original.assert_not_called()
        self.assertEqual(FakeDevice._default_manager.selected_related, [("device_type",)])
        placement_objects.select_for_update.return_value.filter.assert_called_with(device_id__in=[1])

        overlapping = FakeDevice(3, width=2, horizontal_position=1)
        overlapping.rack_id = 1
        self.assertEqual(
            _width_aware_device_placement_conflicts(original, overlapping, object(), 11, "front"),
            [left],
        )

    @patch("netbox_utilities.netbox_export.DeviceRackPlacement.objects")
    def test_import_persists_partial_width_and_removes_stale_full_width(self, placement_objects):
        partial = FakeDevice(1)
        full = FakeDevice(2, width=2, horizontal_position=2)
        partial_placement = WidthAwareDeferredDevicePlacement(None, 11, "front", 2, 1)
        full_placement = WidthAwareDeferredDevicePlacement(None, 12, "front", 1, 1)
        placements = [("partial", partial_placement), ("full", full_placement)]
        resolved = {"partial": partial, "full": full}

        def native_apply(received, *_args, **_kwargs):
            self.assertEqual(received, placements)
            self.assertEqual(partial._netbox_utilities_rack_width, 2)
            self.assertEqual(full._netbox_utilities_rack_width, 1)
            partial.rack_id = full.rack_id = 1
            partial.position = 11
            full.position = 12
            return "saved"

        result = _apply_rack_widths(native_apply, placements, resolved, object(), object())

        self.assertEqual(result, "saved")
        placement_objects.update_or_create.assert_called_once_with(
            device=partial,
            defaults={"width": 2, "horizontal_position": 1},
        )
        placement_objects.filter.assert_called_once_with(device=full)
        placement_objects.filter.return_value.delete.assert_called_once_with()

    @patch("netbox_utilities.netbox_export.import_module")
    @patch("netbox_utilities.netbox_export.apps.get_app_config")
    @patch("netbox_utilities.netbox_export.apps.is_installed", return_value=True)
    def test_installer_patches_supported_netbox_export(self, _installed, get_config, import_module):
        get_config.return_value = SimpleNamespace(version="0.3.11")
        exporter = SimpleNamespace(serialize_object=lambda *args, **kwargs: {})
        graph = SimpleNamespace(is_exportable_model=lambda model: False)
        importer = SimpleNamespace(
            _defer_device_placement=lambda *args, **kwargs: ({}, None),
            _device_placement_conflicts=lambda *args, **kwargs: [],
            _apply_device_placements=lambda *args, **kwargs: None,
        )
        import_module.side_effect = [exporter, graph, importer]

        self.assertTrue(install_netbox_export_rack_width_support())

        for module, name in (
            (exporter, "serialize_object"),
            (graph, "is_exportable_model"),
            (importer, "_defer_device_placement"),
            (importer, "_device_placement_conflicts"),
            (importer, "_apply_device_placements"),
        ):
            self.assertEqual(getattr(getattr(module, name), PATCH_MARKER), PATCH_VERSION)

    @patch("netbox_utilities.netbox_export.import_module")
    @patch("netbox_utilities.netbox_export.apps.get_app_config")
    @patch("netbox_utilities.netbox_export.apps.is_installed", return_value=True)
    def test_installer_ignores_unsupported_netbox_export(self, _installed, get_config, import_module):
        get_config.return_value = SimpleNamespace(version="0.4.0")

        self.assertFalse(install_netbox_export_rack_width_support())
        import_module.assert_not_called()
