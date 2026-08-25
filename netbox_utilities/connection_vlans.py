from copy import deepcopy
from functools import wraps

from ipam.models import VLAN, VLANGroup
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField
from utilities.forms.rendering import FieldSet

from .models import CableVLANAssignment, WirelessLinkVLANAssignment

FORM_FIELD = "utilities_vlans"
GROUP_FILTER_FIELD = "utilities_vlan_group"
PATCH_MARKER = "_netbox_utilities_connection_vlans_installed"


def include_connection_vlans_in_fieldsets(fieldsets):
    """Add the connection VLAN field to an isolated copy of a form layout."""
    if not fieldsets:
        return (FieldSet(GROUP_FILTER_FIELD, FORM_FIELD, name="VLANs der Verbindung"),)

    copied_fieldsets = deepcopy(fieldsets)

    def insert_into_link_group(group):
        items = list(getattr(group, "items", ()))
        if "description" in items or "tags" in items:
            items = [item for item in items if item not in (GROUP_FILTER_FIELD, FORM_FIELD)]
            index = items.index("tags") if "tags" in items else len(items)
            items[index:index] = (GROUP_FILTER_FIELD, FORM_FIELD)
            group.items = tuple(items)
            return True

        for item in items:
            if any(insert_into_link_group(nested) for nested in getattr(item, "groups", ())):
                return True
        return False

    if any(insert_into_link_group(fieldset) for fieldset in copied_fieldsets):
        return tuple(copied_fieldsets)
    return (*copied_fieldsets, FieldSet(GROUP_FILTER_FIELD, FORM_FIELD, name="VLANs der Verbindung"))


def _build_connection_vlan_form(base_form, assignment_model, target_field):
    if getattr(base_form, PATCH_MARKER, False):
        return base_form

    class ConnectionVLANForm(base_form):
        utilities_vlan_group = DynamicModelChoiceField(
            queryset=VLANGroup.objects.all(),
            required=False,
            selector=True,
            label="VLAN-Gruppe (Filter)",
            help_text="Optional: Schränkt die nachfolgende VLAN-Auswahl auf diese Gruppe ein.",
        )
        utilities_vlans = DynamicModelMultipleChoiceField(
            queryset=VLAN.objects.all(),
            required=False,
            selector=True,
            query_params={"group_id": f"${GROUP_FILTER_FIELD}"},
            label="VLANs der Verbindung",
            help_text=(
                "Dokumentiert ein oder mehrere VLANs auf dieser Verbindung. "
                "Die Tagged-/Untagged-VLAN-Einstellungen der Interfaces bleiben unverändert."
            ),
        )

        @property
        def fieldsets(self):
            return include_connection_vlans_in_fieldsets(super().fieldsets)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not self.is_bound and getattr(self.instance, "pk", None):
                assignment = (
                    assignment_model.objects.filter(**{target_field: self.instance}).prefetch_related("vlans").first()
                )
                if assignment is not None:
                    selected_vlans = list(assignment.vlans.all())
                    self.initial[FORM_FIELD] = selected_vlans
                    group_ids = {vlan.group_id for vlan in selected_vlans if getattr(vlan, "group_id", None)}
                    if len(group_ids) == 1:
                        self.initial[GROUP_FILTER_FIELD] = group_ids.pop()

        def save(self, commit=True):
            connection = super().save(commit=commit)
            if commit:
                self._save_connection_vlans(connection)
            else:
                native_save_m2m = self.save_m2m

                def save_m2m():
                    native_save_m2m()
                    self._save_connection_vlans(connection)

                self.save_m2m = save_m2m
            return connection

        def _save_connection_vlans(self, connection):
            selected_vlans = list(self.cleaned_data.get(FORM_FIELD) or ())
            lookup = {target_field: connection}
            if not selected_vlans:
                assignment_model.objects.filter(**lookup).delete()
                return
            assignment, _created = assignment_model.objects.get_or_create(**lookup)
            assignment.vlans.set(selected_vlans)

    ConnectionVLANForm.__name__ = f"ConnectionVLAN{base_form.__name__}"
    ConnectionVLANForm.__qualname__ = ConnectionVLANForm.__name__
    ConnectionVLANForm.__module__ = __name__
    setattr(ConnectionVLANForm, PATCH_MARKER, True)
    return ConnectionVLANForm


def _install_cable_vlan_form():
    import dcim.forms
    from dcim.forms import connections
    from dcim.views import CableEditView

    if getattr(CableEditView, PATCH_MARKER, False):
        return

    native_get_cable_form = dcim.forms.get_cable_form

    @wraps(native_get_cable_form)
    def get_connection_vlan_cable_form(*args, **kwargs):
        base_form = native_get_cable_form(*args, **kwargs)
        return _build_connection_vlan_form(base_form, CableVLANAssignment, "cable")

    setattr(get_connection_vlan_cable_form, PATCH_MARKER, True)
    dcim.forms.get_cable_form = get_connection_vlan_cable_form
    connections.get_cable_form = get_connection_vlan_cable_form
    CableEditView.template_name = "netbox_utilities/cable_edit.html"
    CableEditView.htmx_template_name = "netbox_utilities/cable_edit_form.html"
    setattr(CableEditView, PATCH_MARKER, True)


def _install_wireless_link_vlan_form():
    from wireless.views import WirelessLinkEditView

    if getattr(WirelessLinkEditView, PATCH_MARKER, False):
        return
    WirelessLinkEditView.form = _build_connection_vlan_form(
        WirelessLinkEditView.form,
        WirelessLinkVLANAssignment,
        "wireless_link",
    )
    setattr(WirelessLinkEditView, PATCH_MARKER, True)


def install_connection_vlan_support():
    _install_cable_vlan_form()
    _install_wireless_link_vlan_form()
