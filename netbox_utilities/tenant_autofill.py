from django.core.exceptions import ObjectDoesNotExist
from tenancy.models import Tenant, TenantGroup

from .tenant_scope import active_tenant_scope

PARENT_RELATIONS = (
    "device",
    "virtual_machine",
    "rack",
    "location",
    "site",
    "cluster",
    "circuit",
    "virtual_circuit",
    "tunnel",
    "l2vpn",
    "wireless_lan",
    "power_panel",
)


def tenant_id_from_object(obj, depth=0):
    if obj is None or depth > 3:
        return None
    if isinstance(obj, Tenant):
        return obj.pk

    field_names = {field.name for field in obj._meta.get_fields()}
    if "tenant" in field_names and getattr(obj, "tenant_id", None):
        return obj.tenant_id

    for relation in PARENT_RELATIONS:
        if relation not in field_names:
            continue
        try:
            parent = getattr(obj, relation, None)
        except (ObjectDoesNotExist, ValueError):
            continue
        if tenant_id := tenant_id_from_object(parent, depth + 1):
            return tenant_id
    return None


def _related_object(form, field_name):
    objects = _related_objects(form, field_name)
    return objects[0] if objects else None


def _related_objects(form, field_name):
    field = form.fields.get(field_name)
    if field is None or not hasattr(field, "queryset"):
        return []

    values = []
    if form.is_bound:
        field_name = form.add_prefix(field_name)
        if hasattr(form.data, "getlist"):
            values = form.data.getlist(field_name)
        else:
            values = form.data.get(field_name)
    if not values:
        values = form.initial.get(field_name)
    if not isinstance(values, (list, tuple, set)):
        values = [values]

    objects = [value for value in values if hasattr(value, "_meta")]
    object_ids = [value for value in values if value and not hasattr(value, "_meta")]
    if not object_ids:
        return objects
    try:
        objects.extend(field.queryset.filter(pk__in=object_ids))
    except (TypeError, ValueError):
        pass
    return objects


def _is_cable(instance):
    meta = getattr(instance, "_meta", None)
    return bool(
        meta
        and getattr(meta, "app_label", None) == "dcim"
        and getattr(meta, "model_name", None) == "cable"
    )


def _instance_cable_terminations(instance):
    if not _is_cable(instance):
        return []
    terminations = []
    for name in ("a_terminations", "b_terminations"):
        try:
            values = getattr(instance, name, None) or []
        except (ObjectDoesNotExist, ValueError):
            continue
        terminations.extend(values)
    return terminations


def tenant_id_from_cable_terminations(terminations):
    """Return the common derivable tenant, or None for no/conflicting tenants."""
    tenant_ids = {tenant_id for obj in terminations if (tenant_id := tenant_id_from_object(obj))}
    if len(tenant_ids) == 1:
        return tenant_ids.pop()
    return None


def _cable_form_tenant_result(form):
    instance = getattr(form, "instance", None)
    is_cable_form = _is_cable(instance) or any(name in form.fields for name in ("a_terminations", "b_terminations"))
    if not is_cable_form:
        return None, False

    terminations = []
    for field_name in (
        "a_terminations",
        "b_terminations",
        "termination_a_device",
        "termination_b_device",
        "termination_a_powerpanel",
        "termination_b_powerpanel",
        "termination_a_circuit",
        "termination_b_circuit",
    ):
        terminations.extend(_related_objects(form, field_name))
    if not terminations:
        terminations = _instance_cable_terminations(instance)

    tenant_ids = {tenant_id for obj in terminations if (tenant_id := tenant_id_from_object(obj))}
    if len(tenant_ids) == 1:
        return tenant_ids.pop(), True
    if len(tenant_ids) > 1:
        return None, True
    return None, False


def apply_cable_instance_tenant(instance):
    """Assign a cable's tenant when all derivable terminations agree."""
    if not _is_cable(instance) or getattr(instance, "tenant_id", None):
        return None
    tenant_id = tenant_id_from_cable_terminations(_instance_cable_terminations(instance))
    if tenant_id:
        instance.tenant_id = tenant_id
    return tenant_id


def infer_tenant_id(form):
    instance = getattr(form, "instance", None)
    if instance is not None and getattr(instance, "tenant_id", None):
        return None

    initial_tenant = form.initial.get("tenant")
    if isinstance(initial_tenant, Tenant):
        return initial_tenant.pk
    if initial_tenant:
        try:
            return int(initial_tenant)
        except (TypeError, ValueError):
            pass

    cable_tenant_id, cable_context_found = _cable_form_tenant_result(form)
    if cable_context_found:
        return cable_tenant_id

    for relation in PARENT_RELATIONS:
        if tenant_id := tenant_id_from_object(_related_object(form, relation)):
            return tenant_id

    if instance is not None and (tenant_id := tenant_id_from_object(instance)):
        return tenant_id

    scope = active_tenant_scope.get()
    if scope is not None and scope.kind == "tenant":
        return scope.object_id
    return None


def _tenant_group_field_names(form):
    names = []
    for name, field in form.fields.items():
        queryset = getattr(field, "queryset", None)
        if queryset is not None and queryset.model is TenantGroup:
            names.append(name)
    return names


def _infer_group_id(tenant_id):
    if tenant_id:
        group_id = Tenant.objects.filter(pk=tenant_id).values_list("group_id", flat=True).first()
        if group_id:
            return group_id
    scope = active_tenant_scope.get()
    if scope is not None and scope.kind == "group":
        return scope.object_id
    return None


def apply_tenant_autofill(form):
    tenant_id = None
    tenant_field = form.fields.get("tenant")
    if tenant_field is not None:
        tenant_id = infer_tenant_id(form)
        if tenant_id:
            if not form.is_bound:
                form.initial["tenant"] = tenant_id
            tenant_field.widget.attrs["data-netbox-utilities-autofilled-tenant"] = str(tenant_id)
            tenant_field.help_text = _append_help(
                tenant_field.help_text,
                "Automatisch aus dem Objektkontext oder dem globalen Mandantenfilter vorbelegt.",
            )

    group_id = _infer_group_id(tenant_id)
    if not group_id:
        return
    for name in _tenant_group_field_names(form):
        if getattr(form.instance, f"{name}_id", None) or form.initial.get(name):
            continue
        if not form.is_bound:
            form.initial[name] = group_id
        form.fields[name].help_text = _append_help(
            form.fields[name].help_text,
            "Automatisch aus dem erkannten Mandanten oder der globalen Mandantengruppe vorbelegt.",
        )


def _append_help(existing, addition):
    existing = str(existing or "").strip()
    return f"{existing} {addition}".strip()
