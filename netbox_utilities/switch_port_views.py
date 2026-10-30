from dcim.models import Device, Interface
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone, translation
from django.views import View
from utilities.views import ContentTypePermissionRequiredMixin

from . import switch_port_pdf, switch_ports


def _describe(endpoint):
    device = getattr(endpoint, "device", None) or getattr(endpoint, "parent_object", None)
    if device is not None and device != endpoint:
        return f"{device} – {endpoint}"
    return str(endpoint)


def _peer(interface):
    """Far end through patch panels if the path is complete, otherwise the directly cabled object."""
    try:
        endpoints = interface.connected_endpoints if interface._path_id else []
    except Exception:  # noqa: BLE001 - a broken path must not break the export
        endpoints = []
    if not endpoints and interface.cable_id:
        endpoints = interface.link_peers
    return ", ".join(_describe(endpoint) for endpoint in endpoints or [])


def collect_ports(interfaces):
    ports = []
    for interface in interfaces:
        peer = _peer(interface)
        if not peer and interface.mark_connected:
            peer = switch_ports.MARKED_CONNECTED
        ports.append(
            switch_ports.Port(
                pk=interface.pk,
                name=interface.name,
                label=interface.label,
                type=interface.type,
                type_display=str(interface.get_type_display()),
                enabled=interface.enabled,
                connected=bool(interface.cable_id or interface.mark_connected),
                mgmt_only=interface.mgmt_only,
                description=interface.description,
                peer=peer,
                lag=interface.lag.name if interface.lag_id else "",
                url=interface.get_absolute_url(),
                virtual=interface.type in switch_ports.VIRTUAL_TYPES,
            )
        )
    return ports


def switch_panel_context(request, device):
    """Front panel above the "Device" and "Management" cards, in the user's NetBox language."""
    interfaces = (
        Interface.objects.restrict(request.user, "view")
        .filter(device=device)
        .select_related("lag", "cable", "_path")
        .order_by("_name")
    )
    ports = collect_ports(interfaces)
    switch_ports.assign_vlan_colors(ports)
    texts = switch_ports.PANEL_TEXTS[switch_port_pdf.language(translation.get_language())]
    for port in ports:
        if port.peer == switch_ports.MARKED_CONNECTED:
            port.peer = texts["marked"]
        port.state_text = texts[port.state]
    return {
        "groups": switch_ports.build_groups(ports),
        "summary": switch_ports.summary(ports),
        "legend": switch_ports.vlan_legend(ports),
        "texts": texts,
    }


def device_info(device):
    rack = ""
    if device.rack_id:
        rack = str(device.rack)
        if device.position:
            rack += f" / U{device.position:g}"
    return switch_port_pdf.DeviceInfo(
        name=device.name or str(device),
        site=str(device.site) if device.site_id else "",
        rack=rack,
        model=str(device.device_type),
    )


class SwitchPortsPDFView(ContentTypePermissionRequiredMixin, View):
    """PDF of the port usage of a switch, in the language of the user's NetBox preferences."""

    def get_required_permission(self):
        return "dcim.view_interface"

    def get(self, request, pk):
        device = get_object_or_404(
            Device.objects.restrict(request.user, "view").select_related("site", "rack", "device_type"), pk=pk
        )
        interfaces = (
            Interface.objects.restrict(request.user, "view")
            .filter(device=device)
            .select_related("lag", "cable", "_path")
            .order_by("_name")
        )
        lang = switch_port_pdf.language(translation.get_language())
        pdf = switch_port_pdf.build_pdf(
            device_info(device), collect_ports(interfaces), lang=lang, generated=timezone.localtime()
        )
        filename = f"{switch_port_pdf.TEXTS[lang]['filename']}-{device.name or device.pk}.pdf".replace(" ", "_")
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
