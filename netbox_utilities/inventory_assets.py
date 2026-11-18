import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

COLUMN_NAME = "tenant"


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

    if COLUMN_NAME not in AssetTable.base_columns:
        from utilities.tables import register_table_column

        register_table_column(tables.Column(linkify=True, verbose_name=_("Tenant")), COLUMN_NAME, AssetTable)
    add_to_default_columns(AssetTable)
