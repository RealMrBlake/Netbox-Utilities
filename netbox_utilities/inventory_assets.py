import django_tables2 as tables
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
