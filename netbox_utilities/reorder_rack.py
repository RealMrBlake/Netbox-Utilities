import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib import import_module

from dcim.models import Device, Rack
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import OperationalError, ProgrammingError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from netbox.plugins import get_plugin_config
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from utilities.permissions import get_permission_for_model

from . import __version__
from .models import DeviceRackPlacement
from .rack_width import FULL_WIDTH, effective_width_positions, normalize_width_position, stage_width_position

logger = logging.getLogger(__name__)

SUPPORTED_REORDER_RACK_VERSIONS = {"1.1.4", "1.1.5"}
PATCH_MARKER = "_netbox_utilities_bulk_save"
VIEW_PATCH_MARKER = "_netbox_utilities_width_aware_view"
GRID_COLUMNS = 12
REORDER_RACK_VIEW = "dcim:rack_reorder"


class RackLayoutError(Exception):
    pass


@dataclass(frozen=True)
class DevicePlacement:
    device_id: int
    position: Decimal | None
    face: str
    grid_x: int | None


def grid_dimensions(width, horizontal_position):
    try:
        width, horizontal_position = normalize_width_position(width, horizontal_position)
    except ValidationError as error:
        raise RackLayoutError(str(error)) from error
    grid_width = GRID_COLUMNS // width
    return grid_width, (horizontal_position - 1) * grid_width


def horizontal_position_from_grid_x(width, grid_x):
    if isinstance(grid_x, bool) or not isinstance(grid_x, int):
        raise RackLayoutError("Die horizontale Rasterposition muss eine ganze Zahl sein.")
    grid_width, _ = grid_dimensions(width, 1)
    if grid_x < 0 or grid_x > GRID_COLUMNS - grid_width or grid_x % grid_width:
        raise RackLayoutError(f"Rasterposition {grid_x} ist für 1/{width} Rackbreite nicht zulässig.")
    return grid_x // grid_width + 1


def parse_device_placements(layout, *, grid_columns=None):
    if grid_columns not in {None, GRID_COLUMNS}:
        raise RackLayoutError(f"Das Rackraster muss {GRID_COLUMNS} Spalten verwenden.")

    placements = []
    seen_device_ids = set()

    for section, face in (("front", "front"), ("rear", "rear"), ("other", "")):
        for item in layout[section]:
            if not isinstance(item, dict):
                raise RackLayoutError(f"Ungültiger Eintrag im Bereich {section}.")

            try:
                device_id = int(item["id"])
            except (KeyError, TypeError, ValueError) as error:
                raise RackLayoutError(f"Ein Gerät im Bereich {section} besitzt keine gültige ID.") from error

            if isinstance(item.get("id"), bool) or device_id < 1:
                raise RackLayoutError(f"Ein Gerät im Bereich {section} besitzt keine gültige ID.")
            if device_id in seen_device_ids:
                raise RackLayoutError(f"Gerät {device_id} kommt im Rack-Layout mehrfach vor.")
            seen_device_ids.add(device_id)

            if section == "other":
                position = None
                grid_x = None
            else:
                try:
                    position = Decimal(str(item["y"]))
                except (KeyError, InvalidOperation, TypeError, ValueError) as error:
                    raise RackLayoutError(f"Gerät {device_id} besitzt keine gültige Rack-Position.") from error
                if not position.is_finite():
                    raise RackLayoutError(f"Gerät {device_id} besitzt keine gültige Rack-Position.")

                grid_x = None
                if grid_columns == GRID_COLUMNS:
                    grid_x = item.get("x")
                    if isinstance(grid_x, bool) or not isinstance(grid_x, int) or not 0 <= grid_x < GRID_COLUMNS:
                        raise RackLayoutError(f"Gerät {device_id} besitzt keine gültige horizontale Rasterposition.")

            placements.append(DevicePlacement(device_id=device_id, position=position, face=face, grid_x=grid_x))

    return placements


def apply_rack_layout(*, rack, placements, user):
    placement_by_id = {placement.device_id: placement for placement in placements}
    devices = {
        device.pk: device for device in Device.objects.select_for_update().filter(rack=rack, pk__in=placement_by_id)
    }

    missing_ids = set(placement_by_id) - set(devices)
    if missing_ids:
        missing = ", ".join(str(device_id) for device_id in sorted(missing_ids))
        raise RackLayoutError(f"Diese Geräte gehören nicht zum gewählten Rack: {missing}.")

    stored_placements = {
        placement.device_id: placement
        for placement in DeviceRackPlacement.objects.select_for_update().filter(device_id__in=placement_by_id)
    }
    mounted_devices = [device for device in devices.values() if device.position is not None and device.position > 0]
    effective_placements = effective_width_positions(mounted_devices, stored_placements)
    target_placements = []
    for placement in placements:
        current_width, current_horizontal_position, _source = effective_placements.get(
            placement.device_id,
            (FULL_WIDTH, 1, "default"),
        )
        if placement.position is None:
            target_width, target_horizontal_position = FULL_WIDTH, 1
        elif placement.grid_x is None:
            target_width = current_width
            target_horizontal_position = current_horizontal_position
        else:
            target_width = current_width
            target_horizontal_position = horizontal_position_from_grid_x(target_width, placement.grid_x)
        target_placements.append(
            (
                devices[placement.device_id],
                placement,
                target_width,
                target_horizontal_position,
                current_width,
                current_horizontal_position,
            )
        )

    changed = [
        (device, placement, target_width, target_horizontal_position)
        for (
            device,
            placement,
            target_width,
            target_horizontal_position,
            current_width,
            current_horizontal_position,
        ) in target_placements
        if (
            device.position != placement.position
            or device.face != placement.face
            or current_width != target_width
            or current_horizontal_position != target_horizontal_position
        )
    ]
    if not changed:
        return []

    permission = get_permission_for_model(Device, "change")
    for device, _placement, _width, _horizontal_position in changed:
        if not user.has_perm(permission, obj=device):
            raise PermissionDenied(f"Keine Berechtigung zum Verschieben von {device}.")

    for device, _placement, _width, _horizontal_position in changed:
        device.snapshot()

    changed_ids = [device.pk for device, _placement, _width, _horizontal_position in changed]
    Device.objects.filter(pk__in=changed_ids).update(position=None, face="")

    for device, placement, width, horizontal_position in changed:
        device.position = placement.position
        device.face = placement.face
        stage_width_position(device, width, horizontal_position)
        device.full_clean()
        device.save()

        if width == FULL_WIDTH or placement.position is None:
            DeviceRackPlacement.objects.filter(device=device).delete()
        else:
            DeviceRackPlacement.objects.update_or_create(
                device=device,
                defaults={"width": width, "horizontal_position": horizontal_position},
            )

    return [device for device, _placement, _width, _horizontal_position in changed]


def _validation_error_message(error):
    if hasattr(error, "message_dict"):
        return "; ".join(
            f"{field}: {', '.join(str(message) for message in messages)}"
            for field, messages in error.message_dict.items()
        )
    return "; ".join(str(message) for message in error.messages)


def is_reorder_rack_request(request):
    resolver_match = getattr(request, "resolver_match", None)
    return getattr(resolver_match, "view_name", None) == REORDER_RACK_VIEW


def reorder_rack_width_enabled(request):
    if not (
        is_reorder_rack_request(request)
        and get_plugin_config("netbox_utilities", "reorder_rack_bulk_save_enabled")
        and apps.is_installed("netbox_reorder_rack")
    ):
        return False
    plugin_config = apps.get_app_config("netbox_reorder_rack")
    return getattr(plugin_config, "version", None) in SUPPORTED_REORDER_RACK_VERSIONS


def reorder_grid_y(rack, position, height):
    rack_height = int(Decimal(str(rack.u_height)) * 2)
    grid_height = int(Decimal(str(height)) * 2)
    unit_id = int(Decimal(str(position)) * 2)
    if rack.desc_units:
        return unit_id - 2
    if grid_height > 1:
        return rack_height - unit_id - grid_height + 2
    return rack_height - unit_id


def _image_url(image):
    if not image:
        return ""
    try:
        return image.url
    except (AttributeError, ValueError):
        return ""


def _device_label(device):
    return device.label or str(device.device_type)


def _empty_reorder_rack_width_data(request, *, status="ready"):
    selected_view = request.GET.get("view", "images-and-labels")
    return {
        "columns": GRID_COLUMNS,
        "unit_width": 220,
        "images": selected_view != "labels-only",
        "labels": selected_view != "images-only",
        "devices": [],
        "status": status,
        "schema_version": 3,
        "complete": False,
    }


def get_reorder_rack_width_data(request, *, rack=None, devices=None):
    """Describe every mounted widget for netbox-reorder-rack's GridStack UI."""
    # The patched Reorder view passes its already-authorized rack and device
    # queryset explicitly.  The global helper keeps the permission-scoped
    # lookup for callers which do not own the rendered view.
    view_owned_data = rack is not None
    if not view_owned_data and not reorder_rack_width_enabled(request):
        return None

    data = _empty_reorder_rack_width_data(request)
    rack_id = rack.pk if rack is not None else getattr(request.resolver_match, "kwargs", {}).get("pk")
    if not rack_id:
        data["status"] = "missing-rack"
        return data

    from netbox.config import get_config
    from utilities.html import foreground_color

    try:
        if rack is None:
            rack = Rack.objects.restrict(request.user, "view").filter(pk=rack_id).first()
        if rack is None:
            return None
        if devices is None:
            devices = (
                Device.objects.restrict(request.user, "view")
                .filter(
                    rack=rack,
                    position__gt=0,
                    device_type__u_height__gt=0,
                )
                .select_related(
                    "device_type",
                    "device_type__manufacturer",
                    "role",
                    "virtual_chassis",
                    "netbox_utilities_rack_placement",
                )
                .order_by("position", "pk")
            )
        devices = list(devices)
        widths = effective_width_positions(devices)
        permission = get_permission_for_model(Device, "change")
        for device in devices:
            width, horizontal_position, width_source = widths[device.pk]
            grid_width, grid_x = grid_dimensions(width, horizontal_position)
            role_color = device.role.color or "1685fc"
            grid_height = int(Decimal(str(device.device_type.u_height)) * 2)
            data["devices"].append(
                {
                    "id": device.pk,
                    "label": _device_label(device),
                    "face": device.face,
                    "full_depth": device.device_type.is_full_depth,
                    "grid_x": grid_x,
                    "grid_y": reorder_grid_y(rack, device.position, device.device_type.u_height),
                    "grid_width": grid_width,
                    "grid_height": grid_height,
                    "width": width,
                    "horizontal_position": horizontal_position,
                    "width_source": width_source,
                    "color": role_color,
                    "text_color": foreground_color(role_color),
                    "front_image": _image_url(device.device_type.front_image),
                    "rear_image": _image_url(device.device_type.rear_image),
                    "locked": not request.user.has_perm(permission, obj=device),
                }
            )
        data["unit_width"] = get_config().RACK_ELEVATION_DEFAULT_UNIT_WIDTH
        data["complete"] = True
        return data
    except (
        AttributeError,
        ObjectDoesNotExist,
        OperationalError,
        ProgrammingError,
        RackLayoutError,
        TypeError,
        ValueError,
    ):
        logger.warning(
            "Could not load partial rack widths for netbox-reorder-rack rack %s; using the native rack layout",
            rack_id,
            exc_info=True,
        )
        data["status"] = "native-fallback"
        return data


def bulk_reorder_update(self, request, pk=None):
    serializer = self.serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    layout = serializer.validated_data

    try:
        with transaction.atomic():
            rack = get_object_or_404(Rack.objects.select_for_update(), pk=pk)
            if layout["rack_id"] != rack.pk:
                raise RackLayoutError("Die Rack-ID der Anfrage stimmt nicht mit dem Ziel-Rack überein.")

            grid_columns_header = request.headers.get("X-NetBox-Utilities-Rack-Grid-Columns")
            try:
                grid_columns = int(grid_columns_header) if grid_columns_header is not None else None
            except (TypeError, ValueError):
                raise RackLayoutError("Das angegebene Rackraster ist ungültig.") from None
            placements = parse_device_placements(layout, grid_columns=grid_columns)
            changed_devices = apply_rack_layout(rack=rack, placements=placements, user=request.user)
            if not changed_devices:
                return Response(
                    {"message": "No changes detected."},
                    status=status.HTTP_304_NOT_MODIFIED,
                )

        return Response(
            {
                "message": f"{len(changed_devices)} devices reordered successfully",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )
    except RackLayoutError as error:
        return Response(
            {"message": "Invalid rack layout", "error": str(error)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ValidationError as error:
        return Response(
            {"message": "Invalid device position", "error": _validation_error_message(error)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except PermissionDenied as error:
        return Response(
            {"message": "Permission denied", "error": str(error)},
            status=status.HTTP_403_FORBIDDEN,
        )
    except Http404:
        raise
    except Exception as error:
        logger.exception("Failed to save a reordered rack layout")
        return Response(
            {"message": "Error saving data", "error": str(error)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def width_aware_reorder_get(self, request, pk=None, **kwargs):
    """Render every rack device server-side on the native Reorder page."""
    from dcim.choices import SubdeviceRoleChoices
    from django.conf import settings
    from django.shortcuts import render

    rack = get_object_or_404(Rack, pk=pk)
    selected_view = request.GET.get("view", "images-and-labels")
    images = selected_view != "labels-only"
    labels = selected_view != "images-only"
    non_racked = (
        Device.objects.filter(rack=rack, position__isnull=True, parent_bay__isnull=True)
        .exclude(device_type__subdevice_role=SubdeviceRoleChoices.ROLE_CHILD)
        .select_related("device_type", "role")
    )
    mounted_devices = (
        Device.objects.filter(
            rack=rack,
            position__gt=0,
            device_type__u_height__gt=0,
        )
        .select_related(
            "device_type",
            "device_type__manufacturer",
            "role",
            "virtual_chassis",
            "netbox_utilities_rack_placement",
        )
        .order_by("position", "pk")
    )
    width_data = get_reorder_rack_width_data(request, rack=rack, devices=mounted_devices)
    if not width_data or not width_data.get("complete"):
        original_get = getattr(type(self), "_netbox_utilities_original_get", None)
        if original_get is not None:
            return original_get(self, request, pk=pk, **kwargs)
        raise Http404

    return render(
        request,
        "netbox_utilities/reorder_rack.html",
        {
            "object": rack,
            "images": images,
            "labels": labels,
            "unit_width": width_data["unit_width"],
            "reorder_devices": width_data["devices"],
            "reorder_rack_width_data": width_data,
            "non_racked": non_racked,
            "basepath": settings.BASE_PATH,
            "asset_version": __version__,
        },
    )


def install_reorder_rack_bulk_save():
    if not apps.is_installed("netbox_reorder_rack"):
        return False

    plugin_config = apps.get_app_config("netbox_reorder_rack")
    plugin_version = getattr(plugin_config, "version", None)
    if plugin_version not in SUPPORTED_REORDER_RACK_VERSIONS:
        logger.warning(
            "NetBox Utilities did not patch netbox-reorder-rack version %s; supported versions: %s",
            plugin_version,
            ", ".join(sorted(SUPPORTED_REORDER_RACK_VERSIONS)),
        )
        return False

    api_views = import_module("netbox_reorder_rack.api.views")
    save_viewset = api_views.SaveViewSet
    if not getattr(save_viewset, PATCH_MARKER, False):
        save_viewset._netbox_utilities_original_update = save_viewset.update
        save_viewset.update = bulk_reorder_update
        setattr(save_viewset, PATCH_MARKER, True)

    page_views = import_module("netbox_reorder_rack.views")
    reorder_view = page_views.ReorderView
    if not getattr(reorder_view, VIEW_PATCH_MARKER, False):
        reorder_view._netbox_utilities_original_get = reorder_view.get
        reorder_view.get = width_aware_reorder_get
        setattr(reorder_view, VIEW_PATCH_MARKER, True)

    logger.info("Enabled atomic multi-device saving for netbox-reorder-rack %s", plugin_version)
    return True
