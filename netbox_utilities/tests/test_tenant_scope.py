from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities.tenant_scope import object_matches_tenant


class FakeMeta:
    def __init__(self, *field_names):
        self.fields = [SimpleNamespace(name=name) for name in field_names]

    def get_fields(self):
        return self.fields


class TenantScopeTest(SimpleTestCase):
    def test_direct_tenant_match(self):
        obj = SimpleNamespace(_meta=FakeMeta("tenant"), tenant_id=42)
        self.assertTrue(object_matches_tenant(obj, 42))
        self.assertFalse(object_matches_tenant(obj, 7))

    def test_child_inherits_tenant_from_device(self):
        device = SimpleNamespace(_meta=FakeMeta("tenant"), tenant_id=42)
        interface = SimpleNamespace(_meta=FakeMeta("device"), device=device)
        self.assertTrue(object_matches_tenant(interface, 42))
        self.assertFalse(object_matches_tenant(interface, 7))

    def test_shared_reference_data_remains_visible(self):
        manufacturer = SimpleNamespace(_meta=FakeMeta("name"))
        self.assertTrue(object_matches_tenant(manufacturer, 42))

    def test_unassigned_tenant_object_is_hidden(self):
        obj = SimpleNamespace(_meta=FakeMeta("tenant"), tenant_id=None)
        self.assertFalse(object_matches_tenant(obj, 42))
