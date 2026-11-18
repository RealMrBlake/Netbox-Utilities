import django_tables2 as tables
from django.db.models import Q
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .tenant_autofill import ASSET_HARDWARE_RELATIONS

COLUMN_NAME = "tenant"


def asset_tenant(asset):
    """Tenant of the asset itself, otherwise the tenant of its assigned hardware (or that hardware's device)."""
    if tenant := getattr(asset, "tenant", None):
        return tenant
    for relation in ASSET_HARDWARE_RELATIONS:
        hardware = getattr(asset, relation, None)
        if hardware is None:
            continue
        if tenant := getattr(hardware, "tenant", None):
            return tenant
        if tenant := getattr(getattr(hardware, "device", None), "tenant", None):
            return tenant
    return None


class AssetTenantColumn(tables.Column):
    """Asset tenant, falling back to the tenant of the assigned device, module, inventory item or rack."""

    def render(self, record):
        tenant = asset_tenant(record)
        if tenant is None:
            return "—"
        url = tenant.get_absolute_url() if hasattr(tenant, "get_absolute_url") else None
        return format_html('<a href="{}">{}</a>', url, tenant) if url else str(tenant)


def asset_tenant_query(tenant_ids):
    """Assets whose own tenant, or (without own tenant) whose hardware's tenant, is one of tenant_ids."""
    inherited = Q()
    for path in ("device", "module__device", "inventoryitem__device", "rack"):
        inherited |= Q(**{f"{path}__tenant_id__in": tenant_ids})
    return Q(tenant_id__in=tenant_ids) | (Q(tenant__isnull=True) & inherited)


def _ids(values):
    return [int(getattr(value, "pk", value)) for value in values or () if value not in (None, "")]


def filter_asset_tenant(queryset, name, value):
    tenant_ids = _ids(value)
    return queryset.filter(asset_tenant_query(tenant_ids)) if tenant_ids else queryset


def filter_asset_tenant_group(queryset, name, value):
    from tenancy.models import Tenant, TenantGroup

    group_ids = set()
    for group in TenantGroup.objects.filter(pk__in=_ids(value)):
        group_ids.update(group.get_descendants(include_self=True).values_list("pk", flat=True))
    if not group_ids:
        return queryset
    tenant_ids = list(Tenant.objects.filter(group_id__in=group_ids).values_list("pk", flat=True))
    return queryset.filter(asset_tenant_query(tenant_ids))


def install_asset_tenant_filters():
    """
    Tenant filters include inherited tenants, and the global tenant scope is applied directly.

    The global filter does not rely on the URL parameter injected by the middleware here: any
    invalid or ignored parameter would otherwise silently show all assets.
    """
    from django_filters import ModelMultipleChoiceFilter
    from netbox_inventory.filtersets import AssetFilterSet
    from tenancy.models import Tenant, TenantGroup

    from .tenant_scope import active_tenant_scope

    AssetFilterSet.base_filters["tenant_id"] = ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(),
        field_name="tenant",
        method=filter_asset_tenant,
        label="Tenant (ID), including the tenant of the assigned hardware",
    )
    AssetFilterSet.base_filters["tenant_group_id"] = ModelMultipleChoiceFilter(
        queryset=TenantGroup.objects.all(),
        field_name="tenant__group",
        method=filter_asset_tenant_group,
        label="Tenant group (ID), including the tenant of the assigned hardware",
    )

    if getattr(AssetFilterSet, "_netbox_utilities_scoped", False):
        return
    original_filter_queryset = AssetFilterSet.filter_queryset

    def scoped_filter_queryset(self, queryset):
        queryset = original_filter_queryset(self, queryset)
        scope = active_tenant_scope.get()
        request = getattr(self, "request", None)
        # Like the middleware: the REST API is never filtered implicitly.
        if scope is None or request is None or request.path_info.startswith("/api/"):
            return queryset
        return queryset.filter(asset_tenant_query(list(scope.tenant_ids)))

    AssetFilterSet.filter_queryset = scoped_filter_queryset
    AssetFilterSet._netbox_utilities_scoped = True


def add_to_default_columns(table, column=COLUMN_NAME, after=("status", "asset_tag", "hardware_type")):
    """Show the column by default (users without saved table preferences), next to the status."""
    defaults = [name for name in table.Meta.default_columns if name != column]
    for anchor in after:
        if anchor in defaults:
            defaults.insert(defaults.index(anchor) + 1, column)
            break
    else:
        defaults.append(column)
    table.Meta.default_columns = tuple(defaults)


def install_asset_tenant_column():
    """Show the tenant of every netbox-inventory asset in the asset list."""
    from netbox_inventory.tables import AssetTable
    from utilities.tables import register_table_column

    column = AssetTenantColumn(
        accessor=tables.A("pk"), verbose_name=_("Tenant"), empty_values=(), order_by=("tenant__name",)
    )
    # Replaces the plugin's own column, which stays empty for assets that only inherit a tenant.
    AssetTable.base_columns.pop(COLUMN_NAME, None)
    register_table_column(column, COLUMN_NAME, AssetTable)
    add_to_default_columns(AssetTable)
    install_asset_tenant_filters()
