import re
from collections import defaultdict
from contextvars import ContextVar
from functools import wraps

from django.db import transaction
from django.db.models.signals import post_save

PATCHPANEL_ROLE_NAME = "Patchpanel"

_component_instantiation_active = ContextVar(
    "netbox_utilities_patchpanel_component_instantiation_active",
    default=False,
)


def natural_port_key(port):
    """Return a stable natural-sort key for a front or rear port."""
    name = str(getattr(port, "name", ""))
    parts = tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name))
    return parts, getattr(port, "pk", 0) or 0


def port_identifier(port):
    """Normalize a front/rear port name to its side-independent identifier."""
    name = str(getattr(port, "name", "")).casefold()
    name = re.sub(r"\b(?:front|rear)(?:[\s_-]*port)?(?=\b|\d)", " ", name)
    name = re.sub(r"^(?:fp|rp|f|r)(?=\s*[-_.:/]?\s*\d)", "", name)
    tokens = re.findall(r"\d+|[^\W\d_]+", name)
    identifier = tuple(int(token) if token.isdigit() else token for token in tokens)
    return identifier or None


def is_patchpanel(device):
    role = getattr(device, "role", None)
    return bool(role and str(getattr(role, "name", "")).casefold() == PATCHPANEL_ROLE_NAME.casefold())


def pair_ports(front_ports, rear_ports):
    """Pair only front and rear ports with the same normalized identifier."""
    front_by_identifier = defaultdict(list)
    rear_by_identifier = defaultdict(list)
    for port in front_ports:
        if identifier := port_identifier(port):
            front_by_identifier[identifier].append(port)
    for port in rear_ports:
        if identifier := port_identifier(port):
            rear_by_identifier[identifier].append(port)

    pairs = []
    for identifier, matching_front_ports in front_by_identifier.items():
        matching_rear_ports = rear_by_identifier.get(identifier, [])
        pairs.extend(
            zip(
                sorted(matching_front_ports, key=natural_port_key),
                sorted(matching_rear_ports, key=natural_port_key),
            )
        )
    return sorted(pairs, key=lambda pair: natural_port_key(pair[0]))


def retrace_patchpanel_paths(ports):
    """Retrace cable paths touching any of the supplied pass-through ports."""
    from dcim.models import CablePath

    path_ids = set()
    for port in ports:
        path_ids.update(CablePath.objects.filter(_nodes__contains=port).values_list("pk", flat=True))

    retraced = 0
    for path_id in path_ids:
        if cable_path := CablePath.objects.filter(pk=path_id).first():
            cable_path.retrace()
            retraced += 1
    return retraced


def synchronize_patchpanel(device_id):
    """Enforce front position 1 -> rear position 1 for a Patchpanel device."""
    if not device_id:
        return 0

    from dcim.models import Device, FrontPort, PortMapping, RearPort

    with transaction.atomic():
        device = Device.objects.select_for_update().select_related("role").filter(pk=device_id).first()
        if device is None or not is_patchpanel(device):
            return 0

        front_ports = list(FrontPort.objects.filter(device_id=device_id).only("pk", "name"))
        rear_ports = list(RearPort.objects.filter(device_id=device_id).only("pk", "name"))
        pairs = pair_ports(front_ports, rear_ports)
        expected = {(front.pk, rear.pk, 1, 1) for front, rear in pairs}
        current = set(
            PortMapping.objects.filter(device_id=device_id).values_list(
                "front_port_id",
                "rear_port_id",
                "front_port_position",
                "rear_port_position",
            )
        )
        if current != expected:
            PortMapping.objects.filter(device_id=device_id).delete()
            PortMapping.objects.bulk_create(
                [
                    PortMapping(
                        device_id=device_id,
                        front_port_id=front.pk,
                        rear_port_id=rear.pk,
                        front_port_position=1,
                        rear_port_position=1,
                    )
                    for front, rear in pairs
                ]
            )
            retrace_patchpanel_paths([*front_ports, *rear_ports])
        return len(pairs)


def _component_saved(sender, instance, raw=False, **kwargs):
    if not raw and not _component_instantiation_active.get():
        synchronize_patchpanel(getattr(instance, "device_id", None))


def _wrap_component_container_save(model, device_id_getter):
    marker = "_netbox_utilities_patchpanel_save"
    if getattr(model, marker, False):
        return

    original_save = model.save

    @wraps(original_save)
    def patchpanel_aware_save(instance, *args, **kwargs):
        token = _component_instantiation_active.set(True)
        try:
            result = original_save(instance, *args, **kwargs)
        finally:
            _component_instantiation_active.reset(token)
        synchronize_patchpanel(device_id_getter(instance))
        return result

    model.save = patchpanel_aware_save
    setattr(model, marker, True)


def install_patchpanel_automation():
    from dcim.models import Device, FrontPort, Module, RearPort

    _wrap_component_container_save(Device, lambda device: device.pk)
    _wrap_component_container_save(Module, lambda module: module.device_id)
    post_save.connect(
        _component_saved,
        sender=FrontPort,
        dispatch_uid="netbox_utilities.synchronize_patchpanel_front_ports",
        weak=False,
    )
    post_save.connect(
        _component_saved,
        sender=RearPort,
        dispatch_uid="netbox_utilities.synchronize_patchpanel_rear_ports",
        weak=False,
    )
