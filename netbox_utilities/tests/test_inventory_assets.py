from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities.inventory_assets import add_to_default_columns


def fake_table(*default_columns):
    return SimpleNamespace(Meta=SimpleNamespace(default_columns=default_columns))


class AssetTenantColumnTest(SimpleTestCase):
    def test_tenant_is_shown_after_status(self):
        table = fake_table("pk", "id", "name", "asset_tag", "status", "hardware", "tags")

        add_to_default_columns(table)

        self.assertEqual(table.Meta.default_columns, ("pk", "id", "name", "asset_tag", "status", "tenant", "hardware", "tags"))

    def test_tenant_is_not_duplicated_and_appended_without_anchor(self):
        table = fake_table("pk", "tenant", "name")

        add_to_default_columns(table)

        self.assertEqual(table.Meta.default_columns, ("pk", "name", "tenant"))
