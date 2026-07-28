from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.test import SimpleTestCase
from tenancy.models import Tenant

from netbox_utilities.tenant_validation import model_supports_tenant, validate_tenant_assignment


class FakeMeta:
    def __init__(self, supports_tenant=True):
        self.supports_tenant = supports_tenant

    def get_field(self, name):
        if name != "tenant" or not self.supports_tenant:
            raise FieldDoesNotExist(name)
        return SimpleNamespace(concrete=True, is_relation=True, related_model=Tenant)


class TenantModel:
    _meta = FakeMeta()

    def __init__(self, tenant_id=None):
        self.tenant_id = tenant_id


class SharedModel:
    _meta = FakeMeta(supports_tenant=False)


class TenantValidationTest(SimpleTestCase):
    def test_detects_tenant_capable_model(self):
        self.assertTrue(model_supports_tenant(TenantModel))
        self.assertFalse(model_supports_tenant(SharedModel))

    @patch("netbox_utilities.tenant_validation.tenant_required", return_value=True)
    def test_rejects_missing_tenant_when_required(self, _tenant_required):
        with self.assertRaises(ValidationError) as context:
            validate_tenant_assignment(TenantModel())

        self.assertEqual(context.exception.messages, ["Für dieses Objekt muss ein Mandant angegeben werden."])

    @patch("netbox_utilities.tenant_validation.tenant_required", return_value=True)
    def test_accepts_assigned_tenant(self, _tenant_required):
        validate_tenant_assignment(TenantModel(tenant_id=42))

    @patch("netbox_utilities.tenant_validation.tenant_required", return_value=False)
    def test_allows_missing_tenant_when_disabled(self, _tenant_required):
        validate_tenant_assignment(TenantModel())
