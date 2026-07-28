from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from netbox_utilities.middleware import GlobalTenantFilterMiddleware


class TenantFilterSet:
    base_filters = {"tenant_id": object()}


class SharedFilterSet:
    base_filters = {"status": object()}


def resolver_match(filterset=None, view_name="dcim:device_list"):
    view_class = SimpleNamespace(filterset=filterset)
    return SimpleNamespace(
        func=SimpleNamespace(view_class=view_class),
        namespaces=["dcim"],
        view_name=view_name,
    )


class GlobalTenantFilterMiddlewareTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("netbox_utilities.middleware.resolve")
    def test_injects_and_overrides_tenant_id(self, mocked_resolve):
        mocked_resolve.return_value = resolver_match(TenantFilterSet)
        request = self.factory.get("/dcim/devices/?tenant_id=7&status=active")

        GlobalTenantFilterMiddleware._inject_filter_parameter(request, 42)

        self.assertEqual(request.GET.getlist("tenant_id"), ["42"])
        self.assertEqual(request.GET["status"], "active")

    @patch("netbox_utilities.middleware.resolve")
    def test_does_not_modify_shared_list(self, mocked_resolve):
        mocked_resolve.return_value = resolver_match(SharedFilterSet)
        request = self.factory.get("/dcim/manufacturers/?status=active")

        GlobalTenantFilterMiddleware._inject_filter_parameter(request, 42)

        self.assertNotIn("tenant_id", request.GET)
        self.assertEqual(request.GET["status"], "active")

    @patch("netbox_utilities.middleware.resolve")
    def test_filters_tenant_list_by_primary_key(self, mocked_resolve):
        mocked_resolve.return_value = resolver_match(None, "tenancy:tenant_list")
        request = self.factory.get("/tenancy/tenants/")

        GlobalTenantFilterMiddleware._inject_filter_parameter(request, 42)

        self.assertEqual(request.GET.getlist("id"), ["42"])
