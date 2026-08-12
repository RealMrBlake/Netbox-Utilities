import logging

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.db import OperationalError, ProgrammingError
from netbox.plugins import get_plugin_config

from .models import DeviceRackPlacement

logger = logging.getLogger(__name__)

TOPOLOGY_RACK_ELEVATION_VIEW = "plugins:netbox_topology_views:rack_elevation"


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
    width = int(placement.width)
    horizontal_position = int(placement.horizontal_position)
    return {
        "device_id": placement.device_id,
        "url": placement.device.get_absolute_url(),
        "width": width,
        "horizontal_position": horizontal_position,
        "left_percent": round((horizontal_position - 1) / width * 100, 8),
        "width_percent": round(100 / width, 8),
    }


def get_topology_rack_width_data(request):
    """Return permitted partial-width devices shown by Topology Views."""
    if not topology_rack_width_enabled(request) or not request.GET:
        return None

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

        devices = Device.objects.restrict(request.user, "view").filter(
            rack_id__in=racks.values("pk"),
            position__isnull=False,
        )
        placements = (
            DeviceRackPlacement.objects.filter(device__in=devices).select_related("device").order_by("device_id")
        )
        return [serialize_topology_placement(placement) for placement in placements]
    except (
        AttributeError,
        ObjectDoesNotExist,
        OperationalError,
        ProgrammingError,
        TypeError,
        ValueError,
    ):
        # Keep NetBox usable while plugin migrations are being installed.
        logger.warning("Could not load partial rack widths for NetBox Topology Views", exc_info=True)
        return None
