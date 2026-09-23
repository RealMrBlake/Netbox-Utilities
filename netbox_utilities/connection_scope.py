"""Vorfilter für die B-Seite einer Verkabelung.

Die Felder sind reine Filterfelder: Sie werden nicht gespeichert und können
vom Benutzer geleert werden, um bewusst über Mandanten- oder Standortgrenzen
hinweg zu verkabeln.
"""

import json
from functools import wraps

from dcim.models import Site
from tenancy.models import Tenant, TenantGroup
from utilities.forms.fields import DynamicModelChoiceField

from .tenant_autofill import _related_objects, tenant_id_from_object
from .tenant_scope import active_tenant_scope

TENANT_GROUP_FIELD = "utilities_b_tenant_group"
TENANT_FIELD = "utilities_b_tenant"
SITE_FIELD = "utilities_b_site"
FILTER_FIELDS = (TENANT_GROUP_FIELD, TENANT_FIELD, SITE_FIELD)
PATCH_MARKER = "_netbox_utilities_connection_scope_installed"

A_SIDE_FIELDS = (
    "a_terminations",
    "termination_a_device",
    "termination_a_powerpanel",
    "termination_a_circuit",
)

# Welche Filter der jeweilige FilterSet des B-seitigen Auswahlfelds kennt.
SCOPED_TERMINATION_FIELDS = {
    "termination_b_device": {
        "tenant_group_id": TENANT_GROUP_FIELD,
        "tenant_id": TENANT_FIELD,
        "site_id": SITE_FIELD,
    },
    "termination_b_powerpanel": {
        "site_id": SITE_FIELD,
    },
    "termination_b_circuit": {
        "tenant_group_id": TENANT_GROUP_FIELD,
        "tenant_id": TENANT_FIELD,
        "site_id": SITE_FIELD,
    },
}

HELP_TEXT = (
    "Nur ein Vorfilter für die Auswahl der B-Seite. Wird nicht gespeichert und "
    "kann geleert werden, um jedes Gerät auswählen zu können."
)


def build_filter_fields():
    """Return fresh filter field instances for the B side of a connection."""
    return {
        TENANT_GROUP_FIELD: DynamicModelChoiceField(
            queryset=TenantGroup.objects.all(),
            required=False,
            selector=True,
            label="Mandantengruppe (Filter B-Seite)",
            help_text=HELP_TEXT,
        ),
        TENANT_FIELD: DynamicModelChoiceField(
            queryset=Tenant.objects.all(),
            required=False,
            selector=True,
            query_params={"group_id": f"${TENANT_GROUP_FIELD}"},
            label="Mandant (Filter B-Seite)",
            help_text=HELP_TEXT,
        ),
        SITE_FIELD: DynamicModelChoiceField(
            queryset=Site.objects.all(),
            required=False,
            selector=True,
            label="Standort (Filter B-Seite)",
            help_text=HELP_TEXT,
        ),
    }


def add_query_param(field, name, value):
    """Attach a live query parameter to an already instantiated selection field."""
    query_params = dict(getattr(field, "query_params", None) or {})
    query_params[name] = value
    field.query_params = query_params

    widget = field.widget
    adder = getattr(widget, "add_query_param", None)
    if callable(adder):
        adder(name, value)
        return
    widget.attrs[f"data-query-param-{name}"] = json.dumps([value])


def apply_termination_filters(form):
    """Wire the filter fields into every B-side selection field of the form."""
    for termination_field, filters in SCOPED_TERMINATION_FIELDS.items():
        field = form.fields.get(termination_field)
        if field is None:
            continue
        for query_param, filter_field in filters.items():
            if filter_field in form.fields:
                add_query_param(field, query_param, f"${filter_field}")


def _a_side_objects(form):
    objects = []
    for field_name in A_SIDE_FIELDS:
        objects.extend(_related_objects(form, field_name))
    return objects


def infer_filter_defaults(form):
    """Derive the tenant/site defaults from the A side or the global tenant filter."""
    defaults = {}
    objects = _a_side_objects(form)

    tenant_ids = {tenant_id for obj in objects if (tenant_id := tenant_id_from_object(obj))}
    if len(tenant_ids) == 1:
        defaults[TENANT_FIELD] = tenant_ids.pop()

    site_ids = {site_id for obj in objects if (site_id := _site_id_from_object(obj))}
    if len(site_ids) == 1:
        defaults[SITE_FIELD] = site_ids.pop()

    scope = active_tenant_scope.get()
    if scope is not None:
        if scope.kind == "tenant":
            defaults.setdefault(TENANT_FIELD, scope.object_id)
        elif scope.kind == "group":
            defaults.setdefault(TENANT_GROUP_FIELD, scope.object_id)

    if TENANT_GROUP_FIELD not in defaults and (tenant_id := defaults.get(TENANT_FIELD)):
        group_id = Tenant.objects.filter(pk=tenant_id).values_list("group_id", flat=True).first()
        if group_id:
            defaults[TENANT_GROUP_FIELD] = group_id
    return defaults


def _site_id_from_object(obj, depth=0):
    if obj is None or depth > 3:
        return None
    if isinstance(obj, Site):
        return obj.pk
    if getattr(obj, "site_id", None):
        return obj.site_id
    for relation in ("device", "module", "rack", "location", "power_panel", "circuit"):
        parent = getattr(obj, relation, None)
        if parent is not None and (site_id := _site_id_from_object(parent, depth + 1)):
            return site_id
    return None


def apply_connection_scope(form):
    """Add the B-side filter fields to a connection form and prefill them."""
    for name, field in build_filter_fields().items():
        form.fields.setdefault(name, field)
    apply_termination_filters(form)

    if form.is_bound:
        return
    for name, value in infer_filter_defaults(form).items():
        form.initial.setdefault(name, value)


def _build_scoped_form(base_form):
    if getattr(base_form, PATCH_MARKER, False):
        return base_form

    class ConnectionScopeForm(base_form):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            apply_connection_scope(self)

    ConnectionScopeForm.__name__ = f"ConnectionScope{base_form.__name__}"
    ConnectionScopeForm.__qualname__ = ConnectionScopeForm.__name__
    ConnectionScopeForm.__module__ = __name__
    setattr(ConnectionScopeForm, PATCH_MARKER, True)
    return ConnectionScopeForm


def install_connection_scope_filter():
    """Install the B-side tenant/site prefilter on the cable connect form."""
    import dcim.forms
    from dcim.forms import connections
    from dcim.views import CableEditView

    if getattr(CableEditView, PATCH_MARKER, False):
        return

    native_get_cable_form = dcim.forms.get_cable_form

    @wraps(native_get_cable_form)
    def get_scoped_cable_form(*args, **kwargs):
        return _build_scoped_form(native_get_cable_form(*args, **kwargs))

    setattr(get_scoped_cable_form, PATCH_MARKER, True)
    dcim.forms.get_cable_form = get_scoped_cable_form
    connections.get_cable_form = get_scoped_cable_form
    CableEditView.template_name = "netbox_utilities/cable_edit.html"
    CableEditView.htmx_template_name = "netbox_utilities/cable_edit_form.html"
    setattr(CableEditView, PATCH_MARKER, True)
