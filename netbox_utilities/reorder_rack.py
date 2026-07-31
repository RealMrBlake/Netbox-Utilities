import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib import import_module

from dcim.models import Device, Rack
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from utilities.permissions import get_permission_for_model

logger = logging.getLogger(__name__)

SUPPORTED_REORDER_RACK_VERSIONS = {"1.1.4"}
PATCH_MARKER = "_netbox_utilities_bulk_save"


class RackLayoutError(Exception):
    pass


@dataclass(frozen=True)
class DevicePlacement:
    device_id: int
    position: Decimal | None
    face: str


def parse_device_placements(layout):
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
            else:
                try:
                    position = Decimal(str(item["y"]))
                except (KeyError, InvalidOperation, TypeError, ValueError) as error:
                    raise RackLayoutError(f"Gerät {device_id} besitzt keine gültige Rack-Position.") from error
                if not position.is_finite():
                    raise RackLayoutError(f"Gerät {device_id} besitzt keine gültige Rack-Position.")

            placements.append(DevicePlacement(device_id=device_id, position=position, face=face))

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

    changed = [
        (devices[placement.device_id], placement)
        for placement in placements
        if (
            devices[placement.device_id].position != placement.position
            or devices[placement.device_id].face != placement.face
        )
    ]
    if not changed:
        return []

    permission = get_permission_for_model(Device, "change")
    for device, _placement in changed:
        if not user.has_perm(permission, obj=device):
            raise PermissionDenied(f"Keine Berechtigung zum Verschieben von {device}.")

    for device, _placement in changed:
        device.snapshot()

    changed_ids = [device.pk for device, _placement in changed]
    Device.objects.filter(pk__in=changed_ids).update(position=None, face="")

    for device, placement in changed:
        device.position = placement.position
        device.face = placement.face
        device.full_clean()
        device.save()

    return [device for device, _placement in changed]


def _validation_error_message(error):
    if hasattr(error, "message_dict"):
        return "; ".join(
            f"{field}: {', '.join(str(message) for message in messages)}"
            for field, messages in error.message_dict.items()
        )
    return "; ".join(str(message) for message in error.messages)


def bulk_reorder_update(self, request, pk=None):
    serializer = self.serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    layout = serializer.validated_data

    try:
        with transaction.atomic():
            rack = get_object_or_404(Rack.objects.select_for_update(), pk=pk)
            if layout["rack_id"] != rack.pk:
                raise RackLayoutError("Die Rack-ID der Anfrage stimmt nicht mit dem Ziel-Rack überein.")

            placements = parse_device_placements(layout)
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

    views = import_module("netbox_reorder_rack.api.views")
    save_viewset = views.SaveViewSet
    if getattr(save_viewset, PATCH_MARKER, False):
        return True

    save_viewset._netbox_utilities_original_update = save_viewset.update
    save_viewset.update = bulk_reorder_update
    setattr(save_viewset, PATCH_MARKER, True)
    logger.info("Enabled atomic multi-device saving for netbox-reorder-rack %s", plugin_version)
    return True
