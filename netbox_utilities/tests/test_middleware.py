from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from netbox_utilities.middleware import GlobalTenantFilterMiddleware
from netbox_utilities.tenant_scope import ActiveTenantScope


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

        scope = ActiveTenantScope("tenant", 42, frozenset({42}))
        GlobalTenantFilterMiddleware._inject_filter_parameter(request, scope)

        self.assertEqual(request.GET.getlist("tenant_id"), ["42"])
        self.assertEqual(request.GET["status"], "active")

    @patch("netbox_utilities.middleware.resolve")
    def test_does_not_modify_shared_list(self, mocked_resolve):
        mocked_resolve.return_value = resolver_match(SharedFilterSet)
        request = self.factory.get("/dcim/manufacturers/?status=active")

        scope = ActiveTenantScope("tenant", 42, frozenset({42}))
        GlobalTenantFilterMiddleware._inject_filter_parameter(request, scope)

        self.assertNotIn("tenant_id", request.GET)
        self.assertEqual(request.GET["status"], "active")

    @patch("netbox_utilities.middleware.resolve")
    def test_filters_tenant_list_by_primary_key(self, mocked_resolve):
        mocked_resolve.return_value = resolver_match(None, "tenancy:tenant_list")
        request = self.factory.get("/tenancy/tenants/")

        scope = ActiveTenantScope("tenant", 42, frozenset({42}))
        GlobalTenantFilterMiddleware._inject_filter_parameter(request, scope)

        self.assertEqual(request.GET.getlist("id"), ["42"])

    @patch("netbox_utilities.middleware.resolve")
    def test_injects_tenant_group(self, mocked_resolve):
        class TenantGroupFilterSet:
            base_filters = {"tenant_id": object(), "tenant_group_id": object()}

        mocked_resolve.return_value = resolver_match(TenantGroupFilterSet)
        request = self.factory.get("/dcim/devices/")

        scope = ActiveTenantScope("group", 8, frozenset({42, 43}))
        GlobalTenantFilterMiddleware._inject_filter_parameter(request, scope)

        self.assertEqual(request.GET.getlist("tenant_group_id"), ["8"])

    @patch("netbox_utilities.middleware.resolve")
    def test_group_falls_back_to_tenant_ids(self, mocked_resolve):
        mocked_resolve.return_value = resolver_match(TenantFilterSet)
        request = self.factory.get("/dcim/virtual-chassis/")

        scope = ActiveTenantScope("group", 8, frozenset({42, 43}))
        GlobalTenantFilterMiddleware._inject_filter_parameter(request, scope)

        self.assertCountEqual(request.GET.getlist("tenant_id"), ["42", "43"])

    @patch("netbox_utilities.middleware.resolve")
    def test_tenant_group_list_includes_descendant_groups(self, mocked_resolve):
        mocked_resolve.return_value = resolver_match(None, "tenancy:tenantgroup_list")
        request = self.factory.get("/tenancy/tenant-groups/")

        scope = ActiveTenantScope("group", 8, frozenset({42}), frozenset({8, 9}))
        GlobalTenantFilterMiddleware._inject_filter_parameter(request, scope)

        self.assertCountEqual(request.GET.getlist("id"), ["8", "9"])
