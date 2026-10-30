from dcim.models import ModuleBay
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils import translation
from netbox.plugins import PluginTemplateExtension
from tenancy.models import Tenant, TenantGroup

from . import __version__
from .models import (
    CableVLANAssignment,
    DeviceRackPlacement,
    NavigationPreference,
    WirelessLinkVLANAssignment,
)
from .navigation_helpers import (
    SIDEBAR_WIDTH_DEFAULT,
    SIDEBAR_WIDTH_MAX,
    SIDEBAR_WIDTH_MIN,
    get_visible_menus,
    normalize_preferences,
    normalize_sidebar_width,
)
from .runtime import (
    connection_vlans_enabled,
    hardware_enabled,
    navigation_customization_enabled,
    offline_svg_export_enabled,
    switch_ports_enabled,
    tenant_filter_enabled,
)


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
        return self._switch_ports_button() + self._bulk_module_button()

    def _switch_ports_button(self):
        request, device = self.context["request"], self.context["object"]
        if not switch_ports_enabled() or not request.user.has_perm("dcim.view_interface"):
            return ""
        from . import switch_port_pdf, switch_ports

        if not switch_ports.is_switch(device):
            return ""
        texts = switch_port_pdf.TEXTS[switch_port_pdf.language(translation.get_language())]
        return self.render("netbox_utilities/device_switch_ports_button.html", {"label": texts["button"]})

    def _bulk_module_button(self):
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

    def left_page(self):
        # Rendered into the left column; switch_panel.js moves it above the "Device" and "Management" cards.
        request, device = self.context["request"], self.context["object"]
        if not switch_ports_enabled() or not request.user.has_perm("dcim.view_interface"):
            return ""
        from . import switch_ports
        from .switch_port_views import switch_panel_context

        if not switch_ports.is_switch(device):
            return ""
        return self.render(
            "netbox_utilities/device_switch_panel.html",
            {**switch_panel_context(request, device), "asset_version": __version__},
        )

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


class ClusterHardwareContent(PluginTemplateExtension):
    models = ["virtualization.cluster"]

    def full_width_page(self):
        request = self.context["request"]
        if not hardware_enabled() or not request.user.has_perm("netbox_utilities.view_devicehardware"):
            return ""
        from .hardware_views import cluster_capacity_context

        return self.render(
            "netbox_utilities/cluster_capacity_panel.html", cluster_capacity_context(request, self.context["object"])
        )


class VirtualMachineHardwareContent(PluginTemplateExtension):
    models = ["virtualization.virtualmachine"]

    def right_page(self):
        request = self.context["request"]
        if not hardware_enabled() or not request.user.has_perm("netbox_utilities.view_devicehardware"):
            return ""
        from .hardware_views import vm_host_context

        vm = self.context["object"]
        if vm.device_id is None and vm.cluster_id is None:
            return ""
        return self.render("netbox_utilities/vm_host_panel.html", vm_host_context(request, vm))


class ConnectionVLANContent(PluginTemplateExtension):
    models = ["dcim.cable", "wireless.wirelesslink"]

    def right_page(self):
        if not connection_vlans_enabled():
            return ""

        connection = self.context["object"]
        if connection._meta.label_lower == "dcim.cable":
            assignment_model = CableVLANAssignment
            lookup = {"cable": connection}
        else:
            assignment_model = WirelessLinkVLANAssignment
            lookup = {"wireless_link": connection}

        assignment = assignment_model.objects.filter(**lookup).first()
        if assignment is None:
            return ""

        from ipam.models import VLAN

        visible_vlans = VLAN.objects.restrict(self.context["request"].user, "view").filter(
            pk__in=assignment.vlans.values("pk")
        )
        return self.render(
            "netbox_utilities/connection_vlans_panel.html",
            {"connection_vlans": visible_vlans},
        )


class RackUtilitiesContent(PluginTemplateExtension):
    models = ["dcim.rack"]

    def right_page(self):
        # Injects a script (no visible panel here) which places an "SVG
        # offline" button right next to each native "SVG herunterladen"
        # link, since NetBox renders those inside the per-face elevation
        # cards rather than through a plugin buttons() extension point.
        if not offline_svg_export_enabled():
            return ""
        rack = self.context["object"]
        return self.render(
            "netbox_utilities/rack_offline_svg_panel.html",
            {"rack": rack},
        )


template_extensions = [
    UtilitiesGlobalContent,
    DeviceUtilitiesContent,
    ConnectionVLANContent,
    RackUtilitiesContent,
    ClusterHardwareContent,
    VirtualMachineHardwareContent,
]
