from dcim.models import ModuleBay
from django.middleware.csrf import get_token
from django.urls import reverse
from netbox.plugins import PluginTemplateExtension
from tenancy.models import Tenant, TenantGroup

from . import __version__
from .models import DeviceRackPlacement, NavigationPreference
from .navigation_helpers import (
    SIDEBAR_WIDTH_DEFAULT,
    SIDEBAR_WIDTH_MAX,
    SIDEBAR_WIDTH_MIN,
    get_visible_menus,
    normalize_preferences,
    normalize_sidebar_width,
)
from .runtime import navigation_customization_enabled, tenant_filter_enabled


class UtilitiesGlobalContent(PluginTemplateExtension):
    def head(self):
        request = self.context["request"]
        preference_data = {
            "order": [],
            "hidden": [],
            "menus": [],
            "collapsed": False,
            "width": SIDEBAR_WIDTH_DEFAULT,
        }
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
                "collapsed": preference.sidebar_collapsed if preference else False,
                "width": normalize_sidebar_width(preference.sidebar_width if preference else SIDEBAR_WIDTH_DEFAULT),
                "width_min": SIDEBAR_WIDTH_MIN,
                "width_max": SIDEBAR_WIDTH_MAX,
                "layout_update_url": reverse("plugins:netbox_utilities:navigation_layout"),
                "csrf_token": get_token(request),
            }
        return self.render(
            "netbox_utilities/head.html",
            {
                "frontend_enabled": request.user.is_authenticated,
                "frontend_data": {
                    "image_attachment_add_url": reverse("extras:imageattachment_add"),
                    "bulk_image_upload_url": reverse("plugins:netbox_utilities:bulk_image_upload"),
                },
                "navigation_enabled": request.user.is_authenticated and navigation_customization_enabled(),
                "navigation_preferences": preference_data,
                "asset_version": __version__,
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

    def right_page(self):
        placement = DeviceRackPlacement.objects.filter(device=self.context["object"]).first()
        if placement is None:
            return ""
        return self.render(
            "netbox_utilities/device_rack_width_panel.html",
            {
                "rack_width": f"1/{placement.width}",
                "horizontal_position": placement.horizontal_position,
            },
        )


template_extensions = [UtilitiesGlobalContent, DeviceUtilitiesContent]
