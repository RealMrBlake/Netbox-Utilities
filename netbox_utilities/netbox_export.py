import logging
from dataclasses import dataclass
from decimal import Decimal
from functools import wraps
from importlib import import_module

from django.apps import apps
from django.core.exceptions import ValidationError

from .models import DeviceRackPlacement
from .rack_width import (
    FULL_WIDTH,
    get_width_position,
    normalize_width_position,
    placement_rectangles_overlap,
    stage_width_position,
)

logger = logging.getLogger(__name__)

SUPPORTED_NETBOX_EXPORT_VERSIONS = {"0.3.11"}
RACK_WIDTH_RECORD_KEY = "netbox_utilities_rack_placement"
PATCH_MARKER = "_netbox_utilities_rack_width_version"
PATCH_VERSION = 1


@dataclass(frozen=True)
class WidthAwareDeferredDevicePlacement:
    rack_spec: dict | None
    position: object
    face: object
    width: int
    horizontal_position: int


def _is_device(value):
    return getattr(getattr(value, "_meta", None), "label_lower", None) == "dcim.device"


def _serialize_rack_width(original, obj, *args, **kwargs):
    record = original(obj, *args, **kwargs)
    if _is_device(obj):
        width, horizontal_position = get_width_position(obj)
        record[RACK_WIDTH_RECORD_KEY] = {
            "schema_version": 1,
            "width": width,
            "horizontal_position": horizontal_position,
        }
    return record


def _defer_rack_width(original, model, record):
    prepared, placement = original(model, record)
    if placement is None:
        return prepared, placement

    metadata = record.get(RACK_WIDTH_RECORD_KEY)
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        return prepared, placement
    try:
        width, horizontal_position = normalize_width_position(
            metadata.get("width"),
            metadata.get("horizontal_position"),
        )
    except ValidationError:
        logger.warning("NetBox Export archive contains invalid rack width metadata for %s", record.get("id"))
        return prepared, placement

    return prepared, WidthAwareDeferredDevicePlacement(
        rack_spec=placement.rack_spec,
        position=placement.position,
        face=placement.face,
        width=width,
        horizontal_position=horizontal_position,
    )


def _device_footprint(device):
    device_type = getattr(device, "device_type", None)
    height = Decimal(str(getattr(device_type, "u_height", 1) or 0))
    if height <= 0:
        height = Decimal("0.5")
    return height, bool(getattr(device_type, "is_full_depth", False))


def _width_aware_device_placement_conflicts(original, device, rack, position, face):
    if not _is_device(device):
        return original(device, rack, position, face)
    if rack is None or position is None:
        return []

    width, horizontal_position = get_width_position(device)
    height, full_depth = _device_footprint(device)
    candidates = list(
        type(device)
        ._default_manager.select_for_update()
        .select_related("device_type")
        .filter(rack=rack, position__isnull=False)
        .exclude(pk=device.pk)
    )
    stored_placements = {
        placement.device_id: placement
        for placement in DeviceRackPlacement.objects.select_for_update().filter(
            device_id__in=[candidate.pk for candidate in candidates]
        )
    }
    conflicts = []
    for candidate in candidates:
        candidate_height, candidate_full_depth = _device_footprint(candidate)
        if not (full_depth or candidate_full_depth or candidate.face == face):
            continue
        stored_placement = stored_placements.get(candidate.pk)
        if stored_placement is None:
            candidate_width, candidate_horizontal_position = FULL_WIDTH, 1
        else:
            candidate_width, candidate_horizontal_position = normalize_width_position(
                stored_placement.width,
                stored_placement.horizontal_position,
            )
        if placement_rectangles_overlap(
            position,
            height,
            width,
            horizontal_position,
            candidate.position,
            candidate_height,
            candidate_width,
            candidate_horizontal_position,
        ):
            conflicts.append(candidate)
    return conflicts


def _apply_rack_widths(original, placements, resolved, resolver, compatibility, **kwargs):
    placements = list(placements)
    width_aware = []
    for record_id, placement in placements:
        if not isinstance(placement, WidthAwareDeferredDevicePlacement):
            continue
        device = resolved[record_id]
        stage_width_position(device, placement.width, placement.horizontal_position)
        width_aware.append((device, placement))

    result = original(placements, resolved, resolver, compatibility, **kwargs)

    for device, placement in width_aware:
        if placement.width == FULL_WIDTH or not device.rack_id or not device.position:
            DeviceRackPlacement.objects.filter(device=device).delete()
        else:
            DeviceRackPlacement.objects.update_or_create(
                device=device,
                defaults={
                    "width": placement.width,
                    "horizontal_position": placement.horizontal_position,
                },
            )
    return result


def _rack_placement_is_exportable(original, model):
    if model is DeviceRackPlacement:
        return True
    return original(model)


def _patch_function(module, name, wrapper_factory):
    current = getattr(module, name)
    if getattr(current, PATCH_MARKER, None) == PATCH_VERSION:
        return
    original = current

    @wraps(original)
    def patched(*args, **kwargs):
        return wrapper_factory(original, *args, **kwargs)

    setattr(patched, PATCH_MARKER, PATCH_VERSION)
    setattr(module, name, patched)


def install_netbox_export_rack_width_support():
    if not apps.is_installed("netbox_export"):
        return False

    plugin_config = apps.get_app_config("netbox_export")
    plugin_version = getattr(plugin_config, "version", None)
    if plugin_version not in SUPPORTED_NETBOX_EXPORT_VERSIONS:
        logger.warning(
            "NetBox Utilities did not patch netbox-export version %s; supported versions: %s",
            plugin_version,
            ", ".join(sorted(SUPPORTED_NETBOX_EXPORT_VERSIONS)),
        )
        return False

    exporter = import_module("netbox_export.services.exporter")
    graph = import_module("netbox_export.services.graph")
    importer = import_module("netbox_export.services.importer")
    required = (
        (exporter, "serialize_object"),
        (graph, "is_exportable_model"),
        (importer, "_defer_device_placement"),
        (importer, "_device_placement_conflicts"),
        (importer, "_apply_device_placements"),
    )
    if not all(hasattr(module, name) for module, name in required):
        logger.warning("NetBox Utilities could not find the expected netbox-export 0.3.11 integration hooks")
        return False

    _patch_function(exporter, "serialize_object", _serialize_rack_width)
    _patch_function(graph, "is_exportable_model", _rack_placement_is_exportable)
    _patch_function(importer, "_defer_device_placement", _defer_rack_width)
    _patch_function(importer, "_device_placement_conflicts", _width_aware_device_placement_conflicts)
    _patch_function(importer, "_apply_device_placements", _apply_rack_widths)
    return True
