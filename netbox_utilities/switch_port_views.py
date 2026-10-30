import csv

from dcim.models import Device, Interface
from django.db.models import Q
from django.http import HttpResponse
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from . import switch_ports
from .runtime import switch_ports_enabled


def _connected_query():
    return Q(cable__isnull=False) | Q(mark_connected=True)


def ports_tab_badge(device):
    """ "belegt/gesamt" of the physical ports; None hides the tab for devices that are no switches."""
    if not switch_ports_enabled() or not switch_ports.is_switch(device):
        return None
    physical = Interface.objects.filter(device=device).exclude(type__in=switch_ports.VIRTUAL_TYPES)
    total = physical.count()
    connected = physical.filter(_connected_query(), enabled=True).count()
    return f"{connected}/{total}"


def _describe(endpoint):
    device = getattr(endpoint, "device", None) or getattr(endpoint, "parent_object", None)
    if device is not None and device != endpoint:
        return f"{device} – {endpoint}"
    return str(endpoint)


def _peer(interface):
    """Far end through patch panels if the path is complete, otherwise the directly cabled object."""
    try:
        endpoints = interface.connected_endpoints if interface._path_id else []
    except Exception:  # noqa: BLE001 - a broken path must not break the overview
        endpoints = []
    if not endpoints and interface.cable_id:
        endpoints = interface.link_peers
    if not endpoints:
        return "", ""
    first = endpoints[0]
    text = ", ".join(_describe(endpoint) for endpoint in endpoints)
    url = first.get_absolute_url() if hasattr(first, "get_absolute_url") else ""
    return text, url


def collect_ports(device):
    interfaces = (
        Interface.objects.filter(device=device).select_related("lag", "cable", "_path", "module").order_by("_name")
    )
    ports = []
    for interface in interfaces:
        peer, peer_url = _peer(interface)
        connected = bool(interface.cable_id or interface.mark_connected)
        ports.append(
            switch_ports.Port(
                pk=interface.pk,
                name=interface.name,
                label=interface.label,
                type=interface.type,
                type_display=interface.get_type_display(),
                enabled=interface.enabled,
                connected=connected,
                mgmt_only=interface.mgmt_only,
                description=interface.description,
                peer=peer or ("als verbunden markiert" if interface.mark_connected else ""),
                peer_url=peer_url,
                lag=interface.lag.name if interface.lag_id else "",
                speed=f"{interface.speed // 1000} Mbit/s" if interface.speed else "",
                url=interface.get_absolute_url(),
                virtual=interface.type in switch_ports.VIRTUAL_TYPES,
            )
        )
    return ports


@register_model_view(Device, "ports", path="ports")
class DevicePortsView(generic.ObjectView):
    queryset = Device.objects.all()
    template_name = "netbox_utilities/device_ports.html"
    tab = ViewTab(
        label="Ports",
        badge=ports_tab_badge,
        permission="dcim.view_interface",
        weight=2040,
        hide_if_empty=True,
    )

    def get(self, request, **kwargs):
        if request.GET.get("export") == "csv":
            instance = self.get_object(**kwargs)
            return self.export_csv(instance)
        return super().get(request, **kwargs)

    def get_extra_context(self, request, instance):
        ports = collect_ports(instance)
        return {
            "ports": ports,
            "groups": switch_ports.build_groups(ports),
            "virtual_ports": [port for port in ports if port.virtual],
            "summary": switch_ports.summary(ports),
            "legend": switch_ports.vlan_legend(ports),
            "states": switch_ports.STATE_LABELS,
        }

    @staticmethod
    def export_csv(device):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{device.name or device.pk}-ports.csv"'
        response.write("﻿")  # Excel opens UTF-8 correctly with a BOM
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Port", "Status", "VLAN (Label)", "Gegenstelle", "Beschreibung", "Typ", "LAG", "Speed"])
        for port in collect_ports(device):
            writer.writerow(
                [
                    port.name,
                    port.state_label,
                    port.label,
                    port.peer,
                    port.description,
                    port.type_display,
                    port.lag,
                    port.speed,
                ]
            )
        return response
