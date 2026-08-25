from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django import forms
from django.forms.utils import ErrorDict
from django.template.loader import get_template
from django.test import SimpleTestCase

from netbox_utilities.connection_vlans import (
    FORM_FIELD,
    GROUP_FILTER_FIELD,
    _build_connection_vlan_form,
    include_connection_vlans_in_fieldsets,
)
from netbox_utilities.models import CableVLANAssignment, WirelessLinkVLANAssignment


class ConnectionVLANTest(SimpleTestCase):
    def test_cable_vlan_field_is_rendered_below_b_side(self):
        self.assertIsNotNone(get_template("netbox_utilities/cable_edit_form.html"))
        template_path = Path(__file__).parents[1] / "templates" / "netbox_utilities" / "cable_edit_form.html"
        template = template_path.read_text(encoding="utf-8")

        b_side = template.index('{% trans "B Side" %}')
        group_filter = template.index("{% render_field form.utilities_vlan_group %}")
        vlan_field = template.index("{% render_field form.utilities_vlans %}")
        cable_section = template.index('{% trans "Cable" %}')

        self.assertLess(b_side, group_filter)
        self.assertLess(group_filter, vlan_field)
        self.assertLess(vlan_field, cable_section)
        self.assertEqual(template.count("{% render_field form.utilities_vlan_group %}"), 1)
        self.assertEqual(template.count("{% render_field form.utilities_vlans %}"), 1)

    def test_assignment_models_are_tied_to_their_connection_and_vlans(self):
        self.assertEqual(
            CableVLANAssignment._meta.get_field("cable").remote_field.model._meta.label_lower, "dcim.cable"
        )
        self.assertEqual(
            WirelessLinkVLANAssignment._meta.get_field("wireless_link").remote_field.model._meta.label_lower,
            "wireless.wirelesslink",
        )
        self.assertEqual(CableVLANAssignment._meta.get_field("vlans").remote_field.model._meta.label_lower, "ipam.vlan")
        self.assertEqual(
            WirelessLinkVLANAssignment._meta.get_field("vlans").remote_field.model._meta.label_lower,
            "ipam.vlan",
        )

    def test_connection_vlan_field_is_inserted_into_link_fieldset(self):
        from utilities.forms.rendering import FieldSet

        original = (FieldSet("status", "description", "tags", name="Link"),)

        extended = include_connection_vlans_in_fieldsets(original)

        self.assertEqual(
            extended[0].items,
            ("status", "description", GROUP_FILTER_FIELD, FORM_FIELD, "tags"),
        )
        self.assertEqual(original[0].items, ("status", "description", "tags"))

    def test_resolved_edit_views_expose_connection_vlan_field(self):
        import dcim.forms
        from dcim.models import Interface
        from dcim.views import CableEditView
        from wireless.views import WirelessLinkEditView

        cable_form = dcim.forms.get_cable_form(Interface, Interface)

        self.assertIn(GROUP_FILTER_FIELD, cable_form.base_fields)
        self.assertIn(FORM_FIELD, cable_form.base_fields)
        self.assertEqual(cable_form.base_fields[FORM_FIELD].query_params, {"group_id": f"${GROUP_FILTER_FIELD}"})
        self.assertEqual(CableEditView.template_name, "netbox_utilities/cable_edit.html")
        self.assertEqual(CableEditView.htmx_template_name, "netbox_utilities/cable_edit_form.html")
        self.assertIn(GROUP_FILTER_FIELD, WirelessLinkEditView.form.base_fields)
        self.assertIn(FORM_FIELD, WirelessLinkEditView.form.base_fields)
        self.assertEqual(
            WirelessLinkEditView.form.base_fields[FORM_FIELD].query_params,
            {"group_id": f"${GROUP_FILTER_FIELD}"},
        )

    @patch("netbox_utilities.connection_vlans.CableVLANAssignment.objects")
    def test_form_loads_and_saves_multiple_vlans(self, assignment_objects):
        from dcim.models import Cable
        from utilities.forms.rendering import FieldSet

        class BareCableForm(forms.ModelForm):
            fieldsets = (FieldSet("description", name="Cable"),)

            class Meta:
                model = Cable
                fields = ()

        vlan_a = SimpleNamespace(pk=10, group_id=5)
        vlan_b = SimpleNamespace(pk=20, group_id=5)
        assignment = MagicMock()
        assignment.vlans.all.return_value = [vlan_a, vlan_b]
        assignment_objects.filter.return_value.prefetch_related.return_value.first.return_value = assignment
        assignment_objects.get_or_create.return_value = (assignment, False)
        cable = Cable(pk=7)
        form_class = _build_connection_vlan_form(BareCableForm, CableVLANAssignment, "cable")
        with patch(
            "netbox_utilities.runtime._get_database_settings",
            return_value={"tenant_required": True},
        ):
            form = form_class(instance=cable)

        self.assertEqual(form.initial[FORM_FIELD], [vlan_a, vlan_b])
        self.assertEqual(form.initial[GROUP_FILTER_FIELD], 5)

        form._errors = ErrorDict()
        form.cleaned_data = {FORM_FIELD: [vlan_a, vlan_b]}
        with patch.object(Cable, "save"):
            self.assertIs(form.save(), cable)

        assignment_objects.get_or_create.assert_called_once_with(cable=cable)
        assignment.vlans.set.assert_called_once_with([vlan_a, vlan_b])

    @patch("netbox_utilities.connection_vlans.CableVLANAssignment.objects")
    def test_empty_form_selection_removes_assignment(self, assignment_objects):
        from dcim.models import Cable

        class BareCableForm(forms.ModelForm):
            fieldsets = ()

            class Meta:
                model = Cable
                fields = ()

        cable = Cable(pk=8)
        form_class = _build_connection_vlan_form(BareCableForm, CableVLANAssignment, "cable")
        with patch(
            "netbox_utilities.runtime._get_database_settings",
            return_value={"tenant_required": True},
        ):
            form = form_class(instance=cable)
        form._errors = ErrorDict()
        form.cleaned_data = {FORM_FIELD: []}
        with patch.object(Cable, "save"):
            form.save()

        assignment_objects.filter.assert_called_with(cable=cable)
        assignment_objects.filter.return_value.delete.assert_called_once_with()
        assignment_objects.get_or_create.assert_not_called()
