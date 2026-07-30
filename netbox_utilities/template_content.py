from dcim.models import ModuleBay
from netbox.plugins import PluginTemplateExtension
from tenancy.models import Tenant, TenantGroup

from .models import NavigationPreference
from .navigation_helpers import get_visible_menus, normalize_preferences
from .runtime import navigation_customization_enabled, tenant_filter_enabled


class UtilitiesGlobalContent(PluginTemplateExtension):
    def head(self):
        request = self.context["request"]
        preference_data = {"order": [], "hidden": [], "menus": []}
        if request.user.is_authenticated and navigation_customization_enabled():
            descriptors = get_visible_menus(request.user)
            preference = NavigationPreference.objects.filter(user=request.user).first()
            order, hidden = normalize_preferences(
                preference.menu_order if preference else [],
                preference.hidden_menus if preference else [],
                [item["key"] for item in descriptors],
            )
            preference_data = {
                "order": order,
                "hidden": hidden,
                "menus": descriptors,
            }
        return self.render(
            "netbox_utilities/head.html",
            {
                "navigation_enabled": request.user.is_authenticated and navigation_customization_enabled(),
                "navigation_preferences": preference_data,
            },
        )

    def navbar(self):
        request = self.context["request"]
        if not request.user.is_authenticated or not tenant_filter_enabled():
            return ""

        tenants = Tenant.objects.restrict(request.user, "view").order_by("name")
        tenant_groups = TenantGroup.objects.restrict(request.user, "view").order_by("name")
        return self.render(
            "netbox_utilities/tenant_dropdown.html",
            {
                "tenants": tenants,
                "tenant_groups": tenant_groups,
                "selected_tenant": getattr(request, "netbox_utilities_tenant", None),
                "selected_tenant_group": getattr(request, "netbox_utilities_tenant_group", None),
                "return_url": request.get_full_path(),
            },
        )


class DeviceUtilitiesContent(PluginTemplateExtension):
    models = ["dcim.device"]

    def buttons(self):
        request = self.context["request"]
        device = self.context["object"]
        if not request.user.has_perm("dcim.add_module"):
            return ""
        if (
            not ModuleBay.objects.restrict(request.user, "view")
            .filter(
                device=device,
                enabled=True,
                installed_module__isnull=True,
            )
            .exists()
        ):
            return ""
        return self.render("netbox_utilities/device_bulk_module_button.html")


template_extensions = [UtilitiesGlobalContent, DeviceUtilitiesContent]
