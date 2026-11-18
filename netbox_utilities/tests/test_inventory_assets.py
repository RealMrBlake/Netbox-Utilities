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


class AssetTenantFallbackTest(SimpleTestCase):
    def test_own_tenant_wins_then_hardware_then_hardware_device(self):
        from netbox_utilities.inventory_assets import asset_tenant

        def asset(**kwargs):
            values = dict(tenant=None, device=None, module=None, inventoryitem=None, rack=None)
            return SimpleNamespace(**{**values, **kwargs})

        self.assertEqual(asset_tenant(asset(tenant="A", device=SimpleNamespace(tenant="B"))), "A")
        self.assertEqual(asset_tenant(asset(device=SimpleNamespace(tenant="B"))), "B")
        module = SimpleNamespace(device=SimpleNamespace(tenant="C"))
        self.assertEqual(asset_tenant(asset(module=module)), "C")
        self.assertIsNone(asset_tenant(asset()))
