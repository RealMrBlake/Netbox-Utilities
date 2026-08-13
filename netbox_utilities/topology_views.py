import logging
import re
from functools import wraps
from html import unescape
from importlib import import_module

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.db import OperationalError, ProgrammingError
from django.templatetags.static import static
from django.utils.html import escape, json_script
from netbox.plugins import get_plugin_config

from . import __version__
from .rack_width import effective_width_positions

logger = logging.getLogger(__name__)

TOPOLOGY_RACK_ELEVATION_VIEW = "plugins:netbox_topology_views:rack_elevation"
TOPOLOGY_VIEW_PATCH_MARKER = "_netbox_utilities_rack_width_view"
RACK_DEVICE_TAG_RE = re.compile(
    r"<a\b[^>]*\bclass=[\"'][^\"']*\brack-device\b[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)
HREF_RE = re.compile(r"\bhref=[\"'](?P<url>[^\"']+)[\"']", re.IGNORECASE)
DEVICE_ID_RE = re.compile(r"(?:^|/)dcim/devices/(?P<device_id>\d+)/?(?:$|[?#])")


def is_topology_rack_elevation_request(request):
    resolver_match = getattr(request, "resolver_match", None)
    return getattr(resolver_match, "view_name", None) == TOPOLOGY_RACK_ELEVATION_VIEW


def topology_rack_width_enabled(request):
    """Return whether the optional Topology Views rack integration applies."""
    return bool(
        is_topology_rack_elevation_request(request)
        and get_plugin_config("netbox_utilities", "topology_views_rack_width_enabled")
        and apps.is_installed("netbox_topology_views")
    )


def serialize_topology_placement(placement):
    return serialize_topology_width(
        placement.device,
        placement.width,
        placement.horizontal_position,
        source="stored",
    )


def serialize_topology_width(device, width, horizontal_position, *, source):
    width = int(width)
    horizontal_position = int(horizontal_position)
    return {
        "device_id": device.pk,
        "url": device.get_absolute_url(),
        "width": width,
        "horizontal_position": horizontal_position,
        "left_percent": round((horizontal_position - 1) / width * 100, 8),
        "width_percent": round(100 / width, 8),
        "width_source": source,
    }


def get_topology_rack_width_data(request):
    """Return permitted partial-width devices shown by Topology Views."""
    if not topology_rack_width_enabled(request):
        return None

    data = {"devices": [], "status": "ready", "schema_version": 3, "complete": False}
    if not request.GET:
        return data

    from dcim.models import Device, Rack

    try:
        racks = Rack.objects.restrict(request.user, "view")
        selected_racks = request.GET.getlist("rack_id")
        if selected_racks:
            racks = racks.filter(pk__in=selected_racks)
        else:
            selected_sites = request.GET.getlist("site_id")
            selected_locations = request.GET.getlist("location_id")
            if selected_sites:
                racks = racks.filter(site_id__in=selected_sites)
            if selected_locations:
                racks = racks.filter(location_id__in=selected_locations)

        devices = list(
            Device.objects.restrict(request.user, "view")
            .filter(
                rack_id__in=racks.values("pk"),
                position__gt=0,
                device_type__u_height__gt=0,
            )
            .select_related("device_type", "netbox_utilities_rack_placement")
            .order_by("rack_id", "face", "position", "pk")
        )
        widths = effective_width_positions(devices)
        data["devices"] = [
            serialize_topology_width(device, width, position, source=source)
            for device in devices
            for width, position, source in (widths[device.pk],)
            if width > 1
        ]
        data["complete"] = True
        return data
    except (
        AttributeError,
        ObjectDoesNotExist,
        OperationalError,
        ProgrammingError,
        TypeError,
        ValueError,
    ):
        # Keep NetBox usable while plugin migrations are being installed.
        logger.warning(
            "Could not load partial rack widths for NetBox Topology Views path %s; using its native rack layout",
            request.get_full_path(),
            exc_info=True,
        )
        data["status"] = "native-fallback"
        return data


def _visible_topology_device_urls(html):
    """Return device URLs which the authorized Topology response actually contains."""
    urls = {}
    for tag_match in RACK_DEVICE_TAG_RE.finditer(html):
        href_match = HREF_RE.search(tag_match.group(0))
        if href_match is None:
            continue
        url = unescape(href_match.group("url"))
        device_match = DEVICE_ID_RE.search(url)
        if device_match is not None:
            urls[int(device_match.group("device_id"))] = url
    return urls


def _topology_data_for_visible_devices(visible_urls):
    """Build widths only for devices already exposed by the foreign view."""
    from dcim.models import Device

    devices = list(
        Device.objects.filter(pk__in=visible_urls)
        .select_related("device_type", "netbox_utilities_rack_placement")
        .order_by("rack_id", "face", "position", "pk")
    )
    widths = effective_width_positions(devices)
    result = {"devices": [], "status": "ready", "schema_version": 3, "complete": True}
    for device in devices:
        width, position, source = widths[device.pk]
        if width <= 1:
            continue
        descriptor = serialize_topology_width(device, width, position, source=source)
        descriptor["url"] = visible_urls[device.pk]
        result["devices"].append(descriptor)
    return result


def _css_string(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\a ")


def _topology_width_head(data):
    rules = []
    for device in data["devices"]:
        rules.append(
            f'.rack-device[href="{_css_string(device["url"])}"] {{'
            " right: auto !important;"
            f" left: calc({device['left_percent']}% + 3px) !important;"
            f" width: calc({device['width_percent']}% - 6px) !important;"
            " }"
        )
    stylesheet = f'<style id="netbox-utilities-topology-rack-width-styles">{"".join(rules)}</style>'
    payload = json_script(data, "netbox-utilities-topology-rack-width-data")
    script_url = escape(f"{static('netbox_utilities/topology-rack-width.js')}?v={__version__}")
    return f'{stylesheet}{payload}<script src="{script_url}" defer></script>'


def _inject_topology_widths(response):
    if (
        getattr(response, "streaming", False)
        or getattr(response, "status_code", None) != 200
        or "text/html" not in response.get("Content-Type", "")
    ):
        return response

    html = response.content.decode(response.charset or "utf-8")
    if "</head>" not in html.lower() or "netbox-utilities-topology-rack-width-data" in html:
        return response
    visible_urls = _visible_topology_device_urls(html)
    data = _topology_data_for_visible_devices(visible_urls)
    insertion = _topology_width_head(data)
    head_end = html.lower().index("</head>")
    html = f"{html[:head_end]}{insertion}{html[head_end:]}"
    content = html.encode(response.charset or "utf-8")
    response.content = content
    if response.has_header("Content-Length"):
        response["Content-Length"] = str(len(content))
    return response


def install_topology_rack_width_support():
    """Patch the optional view and derive widths from its authorized HTML."""
    if not (
        apps.is_installed("netbox_topology_views")
        and get_plugin_config("netbox_utilities", "topology_views_rack_width_enabled")
    ):
        return False

    try:
        topology_views = import_module("netbox_topology_views.views")
        view = topology_views.RackElevationView
    except (AttributeError, ImportError):
        logger.warning("NetBox Utilities could not find the optional Topology rack elevation view")
        return False

    if getattr(view, TOPOLOGY_VIEW_PATCH_MARKER, False):
        return True

    original_get = view.get

    @wraps(original_get)
    def width_aware_topology_get(self, request, *args, **kwargs):
        response = original_get(self, request, *args, **kwargs)
        try:
            return _inject_topology_widths(response)
        except (AttributeError, ObjectDoesNotExist, OperationalError, ProgrammingError, TypeError, ValueError):
            logger.warning(
                "Could not inject partial rack widths into NetBox Topology Views path %s",
                request.get_full_path(),
                exc_info=True,
            )
            return response

    view._netbox_utilities_original_get = original_get
    view.get = width_aware_topology_get
    setattr(view, TOPOLOGY_VIEW_PATCH_MARKER, True)
    logger.info("Enabled partial rack widths for the optional Topology rack elevation view")
    return True
