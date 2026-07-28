from django.urls import Resolver404, resolve
from tenancy.models import Tenant

from .runtime import tenant_filter_enabled
from .tenant_scope import active_tenant_id

SESSION_TENANT_KEY = "netbox_utilities.selected_tenant_id"


class GlobalTenantFilterMiddleware:
    """Apply the selected tenant to tenant-aware NetBox list filtersets."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.netbox_utilities_tenant = None
        tenant_id = self._get_selected_tenant_id(request)
        token = active_tenant_id.set(tenant_id)
        try:
            if tenant_id is not None and request.method in {"GET", "HEAD"}:
                self._inject_filter_parameter(request, tenant_id)
            return self.get_response(request)
        finally:
            active_tenant_id.reset(token)

    @staticmethod
    def _get_selected_tenant_id(request):
        if not tenant_filter_enabled() or not request.user.is_authenticated:
            request.session.pop(SESSION_TENANT_KEY, None)
            return None

        tenant_id = request.session.get(SESSION_TENANT_KEY)
        if tenant_id is None:
            return None

        tenant = Tenant.objects.restrict(request.user, "view").filter(pk=tenant_id).first()
        if tenant is None:
            request.session.pop(SESSION_TENANT_KEY, None)
            return None

        request.netbox_utilities_tenant = tenant
        return tenant.pk

    @staticmethod
    def _inject_filter_parameter(request, tenant_id):
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return

        # Plugin, API, login and admin endpoints must never be changed implicitly.
        if "netbox_utilities" in match.namespaces or "api" in match.namespaces:
            return

        parameter = None
        if match.view_name == "tenancy:tenant_list":
            parameter = "id"
        else:
            view_class = getattr(match.func, "view_class", None)
            filterset = getattr(view_class, "filterset", None)
            if filterset and "tenant_id" in getattr(filterset, "base_filters", {}):
                parameter = "tenant_id"

        if parameter:
            query = request.GET.copy()
            query.setlist(parameter, [str(tenant_id)])
            request.GET = query
