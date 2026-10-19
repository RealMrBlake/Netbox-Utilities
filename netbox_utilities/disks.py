"""Pure helpers for the "Datenträger" feature: capacities, RAID maths, warnings and the slot grid."""

import math
import re

from django.utils import timezone

DEFAULT_DISK_DEVICE_ROLES = ("Server", "NAS", "SAN", "MSA")
DEFAULT_AGE_WARNING_YEARS = 5
DEFAULT_WARRANTY_WARNING_DAYS = 90

# Status values which still occupy a slot. "replaced" disks are kept as history only.
STATUS_ACTIVE = "active"
STATUS_SPARE = "spare"
STATUS_FAILED = "failed"
STATUS_PLANNED = "planned"
STATUS_REPLACED = "replaced"
SLOT_OCCUPYING_STATUSES = (STATUS_ACTIVE, STATUS_SPARE, STATUS_FAILED, STATUS_PLANNED)

NUMBERING_HORIZONTAL = "horizontal"
NUMBERING_VERTICAL = "vertical"

_CAPACITY_UNITS = {
    "": 1,
    "G": 1,
    "GB": 1,
    "T": 1000,
    "TB": 1000,
    "P": 1_000_000,
    "PB": 1_000_000,
    "M": 0.001,
    "MB": 0.001,
    "GIB": 1.073741824,
    "TIB": 1099.511627776,
    "PIB": 1_125_899.906842624,
}
_CAPACITY_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)\s*$")


def configured_roles(roles=None):
    """Return the role names which get a "Datenträger" tab, casefolded."""
    if roles is None:
        try:
            from netbox.plugins import get_plugin_config

            roles = get_plugin_config("netbox_utilities", "disk_device_roles")
        except Exception:  # noqa: BLE001 - outside NetBox (tests) fall back to defaults
            roles = None
    return {str(role).casefold() for role in (roles if roles is not None else DEFAULT_DISK_DEVICE_ROLES)}


def supports_disks(device, roles=None):
    role = getattr(device, "role", None)
    return bool(role and str(getattr(role, "name", "")).casefold() in configured_roles(roles))


def parse_capacity(value):
    """Parse "4 TB", "960GB", "1,92 TB" or "4000" (GB) into whole gigabytes (decimal)."""
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return round(value)
    match = _CAPACITY_PATTERN.match(str(value))
    if not match:
        raise ValueError(f"Ungültige Größe: {value!r}. Beispiele: 960 GB, 4 TB, 1,92 TB")
    number = float(match.group(1).replace(",", "."))
    unit = match.group(2).upper()
    if unit not in _CAPACITY_UNITS:
        raise ValueError(f"Unbekannte Einheit {match.group(2)!r}. Erlaubt sind GB, TB, PB, GiB und TiB.")
    gigabytes = round(number * _CAPACITY_UNITS[unit])
    if gigabytes <= 0:
        raise ValueError("Die Größe muss größer als 0 sein.")
    return gigabytes


def format_capacity(gigabytes):
    """Format decimal gigabytes the way disk vendors label them."""
    if gigabytes is None:
        return "—"
    for factor, unit in ((1_000_000, "PB"), (1000, "TB")):
        if gigabytes >= factor:
            text = f"{gigabytes / factor:.2f}".rstrip("0").rstrip(".")
            return f"{text} {unit}".replace(".", ",")
    return f"{gigabytes} GB"


# (minimum members, usable members, tolerated failures) per RAID level; "s" = spans for nested levels.
RAID_LEVELS = {
    "raid0": "RAID 0",
    "raid1": "RAID 1",
    "raid5": "RAID 5",
    "raid6": "RAID 6",
    "raid10": "RAID 10",
    "raid50": "RAID 50",
    "raid60": "RAID 60",
    "raidz1": "RAID-Z1",
    "raidz2": "RAID-Z2",
    "raidz3": "RAID-Z3",
    "jbod": "JBOD",
    "other": "Sonstiges",
}


def raid_usable_capacity(level, sizes, spans=1):
    """Return (usable GB, tolerated disk failures, error text) for a RAID group.

    Mixed sizes are limited to the smallest member, as controllers do. JBOD adds
    all sizes. Unknown levels return no capacity but no error either.
    """
    sizes = [size for size in sizes if size]
    count = len(sizes)
    if count == 0:
        return None, None, None
    smallest = min(sizes)
    spans = max(int(spans or 1), 1)

    if level == "jbod":
        return sum(sizes), 0, None
    if level == "raid0":
        return smallest * count, 0, None
    if level == "raid1":
        if count < 2:
            return None, None, "RAID 1 benötigt mindestens 2 Datenträger."
        return smallest, count - 1, None
    parity = {"raid5": 1, "raidz1": 1, "raid6": 2, "raidz2": 2, "raidz3": 3}
    if level in parity:
        minimum = {"raid5": 3, "raidz1": 2, "raid6": 4, "raidz2": 3, "raidz3": 4}[level]
        if count < minimum:
            return None, None, f"{RAID_LEVELS[level]} benötigt mindestens {minimum} Datenträger."
        return smallest * (count - parity[level]), parity[level], None
    if level == "raid10":
        if count < 4 or count % 2:
            return None, None, "RAID 10 benötigt eine gerade Anzahl von mindestens 4 Datenträgern."
        return smallest * (count // 2), 1, None
    if level in ("raid50", "raid60"):
        per_span_parity = 1 if level == "raid50" else 2
        minimum_per_span = 3 if level == "raid50" else 4
        if spans < 2 or count % spans or count // spans < minimum_per_span:
            return (
                None,
                None,
                (
                    f"{RAID_LEVELS[level]} benötigt mindestens 2 Spans mit je {minimum_per_span} Datenträgern "
                    "und gleich vielen Datenträgern pro Span."
                ),
            )
        return smallest * (count - per_span_parity * spans), per_span_parity, None
    return None, None, None


def add_years(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def disk_age_reference(disk):
    return getattr(disk, "manufacture_date", None) or getattr(disk, "install_date", None)


def disk_warnings(disk, today=None, age_years=DEFAULT_AGE_WARNING_YEARS, warranty_days=DEFAULT_WARRANTY_WARNING_DAYS):
    """Return a list of (level, text) tuples; level is "danger" or "warning"."""
    today = today or timezone.localdate()
    warnings = []
    status = getattr(disk, "status", None)
    if status == STATUS_REPLACED:
        return warnings
    if status == STATUS_FAILED:
        warnings.append(("danger", "Datenträger ist defekt"))

    warranty_end = getattr(disk, "warranty_end", None)
    if warranty_end:
        if warranty_end < today:
            warnings.append(("danger", f"Garantie abgelaufen am {warranty_end:%d.%m.%Y}"))
        elif (warranty_end - today).days <= warranty_days:
            warnings.append(("warning", f"Garantie endet am {warranty_end:%d.%m.%Y}"))

    reference = disk_age_reference(disk)
    if reference and age_years and add_years(reference, age_years) <= today:
        warnings.append(("warning", f"Älter als {age_years} Jahre"))
    return warnings


def warning_settings():
    try:
        from netbox.plugins import get_plugin_config

        return {
            "age_years": get_plugin_config("netbox_utilities", "disk_age_warning_years"),
            "warranty_days": get_plugin_config("netbox_utilities", "disk_warranty_warning_days"),
        }
    except Exception:  # noqa: BLE001
        return {"age_years": DEFAULT_AGE_WARNING_YEARS, "warranty_days": DEFAULT_WARRANTY_WARNING_DAYS}


def slot_numbers(slot_count, first_slot=0):
    return list(range(first_slot, first_slot + slot_count))


def build_slot_grid(slot_count, rows=1, first_slot=0, numbering=NUMBERING_HORIZONTAL, disks_by_slot=None):
    """Arrange slots like the device front: a list of rows, each a list of cells.

    Cells are dicts with "number" and "disk"; padding cells at the end have number None.
    """
    disks_by_slot = disks_by_slot or {}
    rows = min(max(int(rows or 1), 1), max(slot_count, 1))
    columns = math.ceil(slot_count / rows) if slot_count else 0
    grid = [[{"number": None, "disk": None} for _ in range(columns)] for _ in range(rows)]
    for index, number in enumerate(slot_numbers(slot_count, first_slot)):
        if numbering == NUMBERING_VERTICAL:
            row, column = index % rows, index // rows
        else:
            row, column = index // columns, index % columns
        grid[row][column] = {"number": number, "disk": disks_by_slot.get(number)}
    return grid


def parse_serials(text):
    """Split scanner or pasted input (one serial per line, also ; or ,) into a list."""
    return [part.strip() for part in re.split(r"[\r\n;,\t]+", text or "") if part.strip()]


def duplicates(values):
    seen, reported, repeated = set(), set(), []
    for value in values:
        key = value.casefold()
        if key in seen and key not in reported:
            repeated.append(value)
            reported.add(key)
        seen.add(key)
    return repeated


def disk_summary(disks, slot_count):
    """Aggregate the numbers shown above the slot grid."""
    installed = [disk for disk in disks if getattr(disk, "status", None) in SLOT_OCCUPYING_STATUSES]
    raw = sum(disk.capacity_gb or 0 for disk in installed if disk.status != STATUS_PLANNED)
    return {
        "slot_count": slot_count,
        "used": len(installed),
        "free": max(slot_count - len(installed), 0),
        "raw_capacity_gb": raw,
        "spares": sum(1 for disk in installed if disk.status == STATUS_SPARE),
        "failed": sum(1 for disk in installed if disk.status == STATUS_FAILED),
    }
