from django.urls import Resolver404, resolve
from tenancy.models import Tenant, TenantGroup

from .runtime import tenant_filter_enabled
from .tenant_scope import ActiveTenantScope, active_tenant_scope

SESSION_TENANT_KEY = "netbox_utilities.selected_tenant_id"
SESSION_TENANT_GROUP_KEY = "netbox_utilities.selected_tenant_group_id"


class GlobalTenantFilterMiddleware:
    """Apply the selected tenant to tenant-aware NetBox list filtersets."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.netbox_utilities_tenant = None
        request.netbox_utilities_tenant_group = None
        scope = self._get_selected_scope(request)
        token = active_tenant_scope.set(scope)
        try:
            if scope is not None and request.method in {"GET", "HEAD"}:
                self._inject_filter_parameter(request, scope)
            response = self.get_response(request)
            from .topology_views import apply_topology_rack_widths

            return apply_topology_rack_widths(request, response)
        finally:
            active_tenant_scope.reset(token)

    @staticmethod
    def _get_selected_scope(request):
        if not tenant_filter_enabled() or not request.user.is_authenticated:
            GlobalTenantFilterMiddleware.clear_scope(request)
            return None

        tenant_group_id = request.session.get(SESSION_TENANT_GROUP_KEY)
        if tenant_group_id is not None:
            group = TenantGroup.objects.restrict(request.user, "view").filter(pk=tenant_group_id).first()
            if group is None:
                GlobalTenantFilterMiddleware.clear_scope(request)
                return None
            descendant_groups = group.get_descendants(include_self=True)
            group_ids = frozenset(descendant_groups.values_list("pk", flat=True))
            tenant_ids = Tenant.objects.filter(group_id__in=group_ids).values_list("pk", flat=True)
            request.netbox_utilities_tenant_group = group
            return ActiveTenantScope("group", group.pk, frozenset(tenant_ids), group_ids)

        tenant_id = request.session.get(SESSION_TENANT_KEY)
        if tenant_id is None:
            return None

        tenant = Tenant.objects.restrict(request.user, "view").filter(pk=tenant_id).first()
        if tenant is None:
            GlobalTenantFilterMiddleware.clear_scope(request)
            return None

        request.netbox_utilities_tenant = tenant
        return ActiveTenantScope("tenant", tenant.pk, frozenset({tenant.pk}))

    @staticmethod
    def clear_scope(request):
        request.session.pop(SESSION_TENANT_KEY, None)
        request.session.pop(SESSION_TENANT_GROUP_KEY, None)

    @staticmethod
    def _inject_filter_parameter(request, scope):
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return

        # Plugin, API, login and admin endpoints must never be changed implicitly.
        if "netbox_utilities" in match.namespaces or "api" in match.namespaces:
            return

        parameter = None
        values = []
        if match.view_name == "tenancy:tenant_list":
            if scope.kind == "tenant":
                parameter = "id"
                values = [scope.object_id]
            else:
                parameter = "group_id"
                values = [scope.object_id]
        elif match.view_name == "tenancy:tenantgroup_list" and scope.kind == "group":
            parameter = "id"
            values = list(scope.group_ids) or [scope.object_id]
        else:
            view_class = getattr(match.func, "view_class", None)
            filterset = getattr(view_class, "filterset", None)
            base_filters = getattr(filterset, "base_filters", {}) if filterset else {}
            if scope.kind == "tenant" and "tenant_id" in base_filters:
                parameter = "tenant_id"
                values = [scope.object_id]
            elif scope.kind == "group" and "tenant_group_id" in base_filters:
                parameter = "tenant_group_id"
                values = [scope.object_id]
            elif scope.kind == "group" and "tenant_id" in base_filters:
                parameter = "tenant_id"
                values = list(scope.tenant_ids) or [0]

        if parameter:
            query = request.GET.copy()
            query.setlist(parameter, [str(value) for value in values])
            request.GET = query
