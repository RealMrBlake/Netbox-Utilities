import decimal
from contextvars import ContextVar
from fractions import Fraction
from functools import wraps

from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models.signals import post_save, pre_save

from .models import DeviceRackPlacement

FULL_WIDTH = 1
WIDTH_CHOICES = (
    (FULL_WIDTH, "Volle Rackbreite"),
    (2, "1/2 Rackbreite"),
    (3, "1/3 Rackbreite"),
    (4, "1/4 Rackbreite"),
)
POSITION_CHOICES = (
    (1, "Position 1 (links)"),
    (2, "Position 2"),
    (3, "Position 3"),
    (4, "Position 4 (rechts)"),
)
CORE_RACK_POSITION_CONSTRAINT = "dcim_device_unique_rack_position_face"

_validated_device = ContextVar("netbox_utilities_width_validated_device", default=None)


def normalize_width_position(width, horizontal_position):
    try:
        width = int(width or FULL_WIDTH)
        horizontal_position = int(horizontal_position or 1)
    except (TypeError, ValueError):
        raise ValidationError("Rackbreite und Breitenposition sind ungültig.") from None
    if width not in {1, 2, 3, 4}:
        raise ValidationError("Die Rackbreite muss voll, 1/2, 1/3 oder 1/4 sein.")
    if width == FULL_WIDTH:
        return FULL_WIDTH, 1
    if not 1 <= horizontal_position <= width:
        raise ValidationError(f"Für 1/{width} Rackbreite sind nur die Positionen 1 bis {width} möglich.")
    return width, horizontal_position


def horizontal_interval(width, horizontal_position):
    width, horizontal_position = normalize_width_position(width, horizontal_position)
    return Fraction(horizontal_position - 1, width), Fraction(horizontal_position, width)


def intervals_overlap(first, second):
    return max(first[0], second[0]) < min(first[1], second[1])


def intervals_cover_full_width(intervals):
    if not intervals:
        return False
    merged_end = Fraction(0, 1)
    for start, end in sorted(intervals):
        if start > merged_end:
            return False
        merged_end = max(merged_end, end)
    return merged_end >= 1


def placement_rectangles_overlap(
    first_position,
    first_height,
    first_width,
    first_horizontal_position,
    second_position,
    second_height,
    second_width,
    second_horizontal_position,
):
    first_vertical = (
        decimal.Decimal(str(first_position)),
        decimal.Decimal(str(first_position)) + decimal.Decimal(str(first_height)),
    )
    second_vertical = (
        decimal.Decimal(str(second_position)),
        decimal.Decimal(str(second_position)) + decimal.Decimal(str(second_height)),
    )
    return intervals_overlap(first_vertical, second_vertical) and intervals_overlap(
        horizontal_interval(first_width, first_horizontal_position),
        horizontal_interval(second_width, second_horizontal_position),
    )


def _stored_width_position(device):
    if not getattr(device, "pk", None):
        return FULL_WIDTH, 1
    try:
        placement = device.netbox_utilities_rack_placement
    except (AttributeError, ObjectDoesNotExist):
        return FULL_WIDTH, 1
    return placement.width, placement.horizontal_position


def get_width_position(device, placements=None):
    staged_width = getattr(device, "_netbox_utilities_rack_width", None)
    staged_position = getattr(device, "_netbox_utilities_horizontal_position", None)
    if staged_width is not None:
        return normalize_width_position(staged_width, staged_position)
    if placements is not None and device.pk in placements:
        placement = placements[device.pk]
        return placement.width, placement.horizontal_position
    return _stored_width_position(device)


def stage_width_position(device, width, horizontal_position):
    width, horizontal_position = normalize_width_position(width, horizontal_position)
    device._netbox_utilities_rack_width = width
    device._netbox_utilities_horizontal_position = horizontal_position
    return width, horizontal_position


def _vertical_interval(device, position=None):
    start = decimal.Decimal(position if position is not None else device.position)
    height = decimal.Decimal(str(device.device_type.u_height))
    return start, start + height


def _faces_overlap(first, second):
    return bool(first.device_type.is_full_depth or second.device_type.is_full_depth or first.face == second.face)


def _placement_map(device_ids):
    return {
        placement.device_id: placement for placement in DeviceRackPlacement.objects.filter(device_id__in=device_ids)
    }


def find_placement_conflict(device, *, position=None, exclude=None, ignore_excluded_devices=False):
    if not getattr(device, "rack_id", None) or not (position if position is not None else device.position):
        return None
    try:
        candidate_vertical = _vertical_interval(device, position)
    except (AttributeError, ObjectDoesNotExist, TypeError, ValueError):
        return None
    candidate_horizontal = horizontal_interval(*get_width_position(device))

    from dcim.models import Device

    devices = Device.objects.filter(rack_id=device.rack_id, position__gte=1).select_related("device_type")
    excluded_ids = set(exclude or ())
    if device.pk:
        excluded_ids.add(device.pk)
    if excluded_ids:
        devices = devices.exclude(pk__in=excluded_ids)
    if ignore_excluded_devices:
        devices = devices.exclude(device_type__exclude_from_utilization=True)
    devices = list(devices)
    placements = _placement_map([other.pk for other in devices])

    for other in devices:
        if not _faces_overlap(device, other):
            continue
        other_horizontal = horizontal_interval(*get_width_position(other, placements))
        if intervals_overlap(candidate_vertical, _vertical_interval(other)) and intervals_overlap(
            candidate_horizontal,
            other_horizontal,
        ):
            return other
    return None


def validate_device_placement(device):
    if not getattr(device, "rack_id", None) or not getattr(device, "position", None):
        return
    width, horizontal_position = get_width_position(device)
    normalize_width_position(width, horizontal_position)
    if conflict := find_placement_conflict(device):
        raise ValidationError(
            {
                "position": (
                    f"U{device.position} überschneidet sich in der Rackbreite mit dem Gerät {conflict}. "
                    "Wählen Sie eine freie Breitenposition."
                )
            }
        )


def available_units_for_device(rack, device, *, exclude=None, ignore_excluded_devices=False):
    try:
        height = decimal.Decimal(str(device.device_type.u_height))
    except (AttributeError, ObjectDoesNotExist):
        return []
    if not device.position:
        return []
    units = list(rack.units)
    required = set(_decimal_range(device.position, decimal.Decimal(device.position) + height))
    if not required.issubset(units):
        return []
    conflict = find_placement_conflict(
        device,
        exclude=exclude,
        ignore_excluded_devices=ignore_excluded_devices,
    )
    return [device.position] if conflict is None else []


def _decimal_range(start, stop):
    current = decimal.Decimal(start)
    stop = decimal.Decimal(stop)
    while current < stop:
        yield current
        current += decimal.Decimal("0.5")


def _partial_intervals_for_unit(unit, face, placements):
    intervals = []
    for placement in placements:
        device = placement.device
        if not (device.face == face or device.device_type.is_full_depth):
            continue
        start, end = _vertical_interval(device)
        if start <= decimal.Decimal(unit) < end:
            intervals.append(horizontal_interval(placement.width, placement.horizontal_position))
    return intervals


def _install_rack_methods():
    from dcim.models import Rack

    if getattr(Rack, "_netbox_utilities_rack_width_installed", False):
        return
    original_available_units = Rack.get_available_units
    original_rack_units = Rack.get_rack_units

    @wraps(original_available_units)
    def width_aware_available_units(
        rack,
        u_height=1.0,
        rack_face=None,
        exclude=None,
        ignore_excluded_devices=False,
    ):
        device = _validated_device.get()
        if device is not None and getattr(device, "rack_id", None) == rack.pk:
            return available_units_for_device(
                rack,
                device,
                exclude=exclude,
                ignore_excluded_devices=ignore_excluded_devices,
            )
        return original_available_units(rack, u_height, rack_face, exclude, ignore_excluded_devices)

    @wraps(original_rack_units)
    def width_aware_rack_units(rack, *args, **kwargs):
        units = original_rack_units(rack, *args, **kwargs)
        face = kwargs.get("face")
        if face is None and len(args) > 1:
            face = args[1]
        if face is None:
            from dcim.choices import DeviceFaceChoices

            face = DeviceFaceChoices.FACE_FRONT
        placements = list(
            DeviceRackPlacement.objects.filter(
                device__rack=rack,
                device__position__isnull=False,
            ).select_related("device", "device__device_type")
        )
        for unit in units:
            intervals = _partial_intervals_for_unit(unit["id"], face, placements)
            if not intervals:
                continue
            unit["device"] = None
            unit.pop("height", None)
            unit["occupied"] = intervals_cover_full_width(intervals)
        return units

    Rack.get_available_units = width_aware_available_units
    Rack.get_rack_units = width_aware_rack_units
    Rack._netbox_utilities_rack_width_installed = True


def _install_device_validation():
    from dcim.models import Device

    if getattr(Device, "_netbox_utilities_rack_width_installed", False):
        return
    original_clean = Device.clean

    @wraps(original_clean)
    def width_aware_clean(device, *args, **kwargs):
        token = _validated_device.set(device)
        try:
            result = original_clean(device, *args, **kwargs)
        finally:
            _validated_device.reset(token)
        validate_device_placement(device)
        return result

    Device.clean = width_aware_clean
    Device._meta.constraints = tuple(
        constraint
        for constraint in Device._meta.constraints
        if not (
            constraint.name == CORE_RACK_POSITION_CONSTRAINT
            or tuple(getattr(constraint, "fields", ())) == ("rack", "position", "face")
        )
    )
    Device._meta.__dict__.pop("total_unique_constraints", None)
    Device._netbox_utilities_rack_width_installed = True


def _install_device_form():
    from dcim.forms import DeviceForm

    if getattr(DeviceForm, "_netbox_utilities_rack_width_installed", False):
        return

    original_init = DeviceForm.__init__
    original_clean = DeviceForm.clean
    original_save = DeviceForm.save

    @wraps(original_init)
    def width_aware_init(form, *args, **kwargs):
        original_init(form, *args, **kwargs)
        width, horizontal_position = _stored_width_position(form.instance)
        form.fields["utilities_rack_width"] = forms.ChoiceField(
            label="Rackbreite",
            choices=WIDTH_CHOICES,
            required=False,
            initial=width,
            help_text="Optional: Geräte können sich eine HE nebeneinander teilen.",
        )
        form.fields["utilities_horizontal_position"] = forms.ChoiceField(
            label="Breitenposition",
            choices=POSITION_CHOICES,
            required=False,
            initial=horizontal_position,
            help_text="Position von links; bei halber Breite sind Position 1 und 2 möglich.",
        )
        if not form.is_bound:
            form.initial["utilities_rack_width"] = width
            form.initial["utilities_horizontal_position"] = horizontal_position

        reordered = {}
        for name, field in form.fields.items():
            if name in {"utilities_rack_width", "utilities_horizontal_position"}:
                continue
            reordered[name] = field
            if name == "face":
                reordered["utilities_rack_width"] = form.fields["utilities_rack_width"]
                reordered["utilities_horizontal_position"] = form.fields["utilities_horizontal_position"]
        form.fields = reordered

    @wraps(original_clean)
    def width_aware_form_clean(form):
        cleaned_data = original_clean(form)
        try:
            width, horizontal_position = normalize_width_position(
                cleaned_data.get("utilities_rack_width"),
                cleaned_data.get("utilities_horizontal_position"),
            )
        except ValidationError as error:
            form.add_error("utilities_horizontal_position", error)
            return cleaned_data
        if not cleaned_data.get("rack") or not cleaned_data.get("position"):
            width, horizontal_position = FULL_WIDTH, 1
        cleaned_data["utilities_rack_width"] = width
        cleaned_data["utilities_horizontal_position"] = horizontal_position
        stage_width_position(form.instance, width, horizontal_position)
        return cleaned_data

    @wraps(original_save)
    def width_aware_form_save(form, commit=True):
        device = original_save(form, commit=commit)
        if not commit:
            return device
        width, horizontal_position = get_width_position(device)
        if width == FULL_WIDTH or not device.rack_id or not device.position:
            DeviceRackPlacement.objects.filter(device=device).delete()
        else:
            DeviceRackPlacement.objects.update_or_create(
                device=device,
                defaults={"width": width, "horizontal_position": horizontal_position},
            )
        return device

    DeviceForm.__init__ = width_aware_init
    DeviceForm.clean = width_aware_form_clean
    DeviceForm.save = width_aware_form_save
    DeviceForm._netbox_utilities_rack_width_installed = True


def _install_rack_svg():
    from dcim.svg.racks import RackElevationSVG

    if getattr(RackElevationSVG, "_netbox_utilities_rack_width_installed", False):
        return
    original_draw_face = RackElevationSVG.draw_face

    @wraps(original_draw_face)
    def width_aware_draw_face(elevation, face, opposite=False):
        original_draw_face(elevation, face, opposite)
        placements = DeviceRackPlacement.objects.filter(
            device__rack=elevation.rack,
            device__position__isnull=False,
        ).select_related("device", "device__device_type", "device__role")
        for placement in placements:
            device = placement.device
            if not (device.face == face or device.device_type.is_full_depth):
                continue
            height = decimal.Decimal(str(device.device_type.u_height))
            coords = elevation._get_device_coords(device.position, height)
            width = elevation.unit_width / placement.width
            coords = (coords[0] + width * (placement.horizontal_position - 1), coords[1])
            size = (width, int(elevation.unit_height * height))
            if device.pk in elevation.permitted_device_ids:
                if device.face == face and not opposite:
                    elevation.draw_device_front(device, coords, size)
                else:
                    elevation.draw_device_rear(device, coords, size)
            else:
                from svgwrite.shapes import Rect

                elevation.drawing.add(Rect(coords, size, class_="blocked"))

    RackElevationSVG.draw_face = width_aware_draw_face
    RackElevationSVG._netbox_utilities_rack_width_installed = True


def _validate_before_save(sender, instance, raw=False, **kwargs):
    if not raw:
        using = kwargs.get("using")
        if instance.rack_id:
            from dcim.models import Rack
            from django.db import transaction

            connection = transaction.get_connection(using)
            if connection.in_atomic_block:
                Rack.objects.using(using).select_for_update().filter(pk=instance.rack_id).exists()
        validate_device_placement(instance)


def _cleanup_unracked_placement(sender, instance, raw=False, using=None, **kwargs):
    if not raw and (not instance.rack_id or not instance.position):
        DeviceRackPlacement.objects.using(using).filter(device_id=instance.pk).delete()


def install_rack_width_support():
    from dcim.models import Device

    _install_rack_methods()
    _install_device_validation()
    _install_device_form()
    _install_rack_svg()
    pre_save.connect(
        _validate_before_save,
        sender=Device,
        dispatch_uid="netbox_utilities.validate_device_rack_width",
        weak=False,
    )
    post_save.connect(
        _cleanup_unracked_placement,
        sender=Device,
        dispatch_uid="netbox_utilities.cleanup_device_rack_width",
        weak=False,
    )
