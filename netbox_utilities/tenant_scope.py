from contextvars import ContextVar
from functools import wraps

from tenancy.models import Tenant

active_tenant_id = ContextVar("netbox_utilities_active_tenant_id", default=None)

_PARENT_RELATIONS = (
    "device",
    "virtual_machine",
    "site",
    "location",
    "rack",
    "cluster",
    "circuit",
    "virtual_circuit",
    "tunnel",
    "l2vpn",
    "wireless_lan",
    "power_panel",
)


def object_matches_tenant(obj, tenant_id, depth=0):
    """
    Return whether a search result belongs to the selected tenant.

    Models without tenant semantics are shared reference data and remain visible.
    Child objects inherit tenant membership from a known parent relationship.
    """
    if obj is None:
        return False
    if isinstance(obj, Tenant):
        return obj.pk == tenant_id

    field_names = {field.name for field in obj._meta.get_fields()}
    if "tenant" in field_names:
        return getattr(obj, "tenant_id", None) == tenant_id

    if depth < 2:
        for relation in _PARENT_RELATIONS:
            if relation not in field_names:
                continue
            parent = getattr(obj, relation, None)
            if parent is None:
                return False
            return object_matches_tenant(parent, tenant_id, depth + 1)

    # Global reference objects (roles, manufacturers, statuses, etc.) are not
    # tenant-owned and must remain usable while a filter is active.
    return True


def install_search_filter():
    """Install the tenant scope around NetBox's singleton global search backend."""
    from netbox.search.backends import search_backend

    if getattr(search_backend, "_netbox_utilities_wrapped", False):
        return

    original_search = search_backend.search

    @wraps(original_search)
    def tenant_aware_search(*args, **kwargs):
        results = original_search(*args, **kwargs)
        tenant_id = active_tenant_id.get()
        if tenant_id is None:
            return results
        return [result for result in results if object_matches_tenant(result.object, tenant_id)]

    search_backend.search = tenant_aware_search
    search_backend._netbox_utilities_wrapped = True
