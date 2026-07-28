from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps

from tenancy.models import Tenant


@dataclass(frozen=True)
class ActiveTenantScope:
    kind: str
    object_id: int
    tenant_ids: frozenset[int]
    group_ids: frozenset[int] = frozenset()


active_tenant_scope = ContextVar("netbox_utilities_active_tenant_scope", default=None)

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
    return object_matches_tenant_ids(obj, frozenset({tenant_id}), depth=depth)


def object_matches_tenant_ids(obj, tenant_ids, depth=0):
    """
    Return whether a search result belongs to the selected tenant.

    Models without tenant semantics are shared reference data and remain visible.
    Child objects inherit tenant membership from a known parent relationship.
    """
    if obj is None:
        return False
    if isinstance(obj, Tenant):
        return obj.pk in tenant_ids

    field_names = {field.name for field in obj._meta.get_fields()}
    if "tenant" in field_names:
        return getattr(obj, "tenant_id", None) in tenant_ids

    if depth < 2:
        for relation in _PARENT_RELATIONS:
            if relation not in field_names:
                continue
            parent = getattr(obj, relation, None)
            if parent is None:
                return False
            return object_matches_tenant_ids(parent, tenant_ids, depth + 1)

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
        scope = active_tenant_scope.get()
        if scope is None:
            return results
        return [result for result in results if object_matches_tenant_ids(result.object, scope.tenant_ids)]

    search_backend.search = tenant_aware_search
    search_backend._netbox_utilities_wrapped = True
