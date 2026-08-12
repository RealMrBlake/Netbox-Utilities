from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.context_processors import PermWrapper
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from netbox_utilities.rack_width import (
    _cleanup_unracked_placement,
    _fit_latest_elevation_image,
    _partial_width_elevation_devices,
    available_units_for_device,
    horizontal_interval,
    include_rack_width_in_fieldsets,
    intervals_cover_full_width,
    intervals_overlap,
    normalize_width_position,
    placement_rectangles_overlap,
    stage_width_position,
)


class RackWidthTest(SimpleTestCase):
    def test_rack_width_javascript_synchronizes_netbox_tom_select(self):
        script = (Path(__file__).parents[1] / "static" / "netbox_utilities" / "forms.js").read_text(encoding="utf-8")

        self.assertIn("positionField.disabled = width === 1", script)
        self.assertIn("positionField.tomselect.sync()", script)

    def test_partial_width_device_image_is_fitted_without_cropping(self):
        from svgwrite import Drawing
        from svgwrite.container import Hyperlink
        from svgwrite.image import Image

        drawing = Drawing()
        link = Hyperlink("/dcim/devices/1/")
        device_image = Image("/media/device.png", size=(100, 20))
        device_image.fit(scale="slice")
        link.add(device_image)
        drawing.add(link)

        _fit_latest_elevation_image(drawing)

        self.assertEqual(device_image.attribs["preserveAspectRatio"], "xMidYMid meet")

    def test_partial_width_svg_devices_include_core_device_bay_annotation(self):
        from dcim.choices import DeviceFaceChoices
        from dcim.models import Rack

        devices = _partial_width_elevation_devices(Rack(pk=3), DeviceFaceChoices.FACE_FRONT)

        self.assertIn("devicebay_count", devices.query.annotations)
        self.assertIn("netbox_utilities_rack_placement", devices.query.select_related)
        self.assertIn("device_type", devices.query.select_related)
        self.assertIn("manufacturer", devices.query.select_related["device_type"])

    def test_adds_rack_width_fields_to_existing_location_fieldset(self):
        from utilities.forms.rendering import FieldSet

        original = (FieldSet("site", "rack", "position", "latitude", name="Location"),)

        extended = include_rack_width_in_fieldsets(original)

        self.assertEqual(
            extended[0].items,
            (
                "site",
                "rack",
                "position",
                "utilities_rack_width",
                "utilities_horizontal_position",
                "latitude",
            ),
        )
        self.assertEqual(original[0].items, ("site", "rack", "position", "latitude"))

    def test_appends_visible_fallback_fieldset_when_position_is_missing(self):
        from utilities.forms.rendering import FieldSet

        extended = include_rack_width_in_fieldsets((FieldSet("name", name="Device"),))

        self.assertEqual(extended[-1].name, "Rackbreite im Rack")
        self.assertEqual(extended[-1].items, ("utilities_rack_width", "utilities_horizontal_position"))

    def test_device_edit_view_uses_explicit_rack_width_form(self):
        from netbox.registry import registry

        edit_view = next(view["view"] for view in registry["views"]["dcim"]["device"] if view["name"] == "edit")

        self.assertEqual(edit_view.__name__, "RackWidthDeviceEditView")
        self.assertEqual(edit_view.form.__name__, "RackWidthDeviceForm")
        self.assertEqual(edit_view.template_name, "netbox_utilities/device_edit.html")
        self.assertEqual(edit_view.htmx_template_name, "netbox_utilities/device_edit_form.html")
        self.assertIn("utilities_rack_width", edit_view.form.base_fields)
        self.assertIn("utilities_horizontal_position", edit_view.form.base_fields)

    def test_resolved_device_edit_page_renders_rack_width_fields(self):
        from dcim.models import Device

        object_type = SimpleNamespace(pk=1, model_class=lambda: Device)
        with (
            patch("core.models.ObjectType.objects.get_for_model", return_value=object_type),
            patch(
                "django.contrib.contenttypes.models.ContentType.objects.get_for_model",
                return_value=object_type,
            ),
            patch("extras.models.CustomField.objects.get_for_model", return_value=[]),
            patch(
                "netbox_utilities.runtime._get_database_settings",
                return_value={"tenant_required": True},
            ),
        ):
            url = reverse("dcim:device_edit", kwargs={"pk": 1})
            view_class = resolve(url).func.view_class
            form = view_class.form()
            request = self._anonymous_request()
            context = {
                "form": form,
                "object": SimpleNamespace(
                    pk=None,
                    _meta=Device._meta,
                    device_type=SimpleNamespace(is_child_device=False),
                    parent_bay=None,
                ),
                "return_url": "/dcim/devices/",
                "request": request,
                "settings": settings,
                "csrf_token": "",
                "perms": PermWrapper(request.user),
            }
            rendered_pages = (
                render_to_string(view_class.htmx_template_name, context),
                render_to_string(view_class.template_name, context),
            )

        rack_position = 'name="position"'
        width = 'name="utilities_rack_width"'
        horizontal_position = 'name="utilities_horizontal_position"'
        latitude = 'name="latitude"'
        for html in rendered_pages:
            self.assertIn(width, html)
            self.assertIn(horizontal_position, html)
            self.assertLess(html.index(rack_position), html.index(width))
            self.assertLess(html.index(width), html.index(horizontal_position))
            self.assertLess(html.index(horizontal_position), html.index(latitude))

    def test_bound_device_form_clean_handles_netbox_clean_returning_none(self):
        from dcim.models import Device
        from netbox.registry import registry

        edit_view = next(view["view"] for view in registry["views"]["dcim"]["device"] if view["name"] == "edit")
        object_type = SimpleNamespace(pk=1, model_class=lambda: Device)
        with (
            patch("core.models.ObjectType.objects.get_for_model", return_value=object_type),
            patch(
                "django.contrib.contenttypes.models.ContentType.objects.get_for_model",
                return_value=object_type,
            ),
            patch("extras.models.CustomField.objects.get_for_model", return_value=[]),
            patch(
                "netbox_utilities.runtime._get_database_settings",
                return_value={"tenant_required": True},
            ),
        ):
            form = edit_view.form(data={})
            # NetBox 4.6.7's CheckLastUpdatedMixin.clean() updates
            # self.cleaned_data but deliberately returns None.
            with patch.object(form, "_post_clean"):
                self.assertFalse(form.is_valid())
            self.assertIsInstance(form.cleaned_data, dict)

    @staticmethod
    def _anonymous_request():
        request = RequestFactory().get("/dcim/devices/1/edit/")
        request.user = AnonymousUser()
        return request

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
