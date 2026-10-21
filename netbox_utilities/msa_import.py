"""Pure helpers for importing CSV exports of an HPE MSA: the disk list and the disk group list.

Column names are matched loosely: case, spaces and punctuation are ignored and common
alternative names are accepted, so slightly different firmware versions or re-saved
files (Excel with semicolons, other encodings) still work.
"""

import csv
import io
import re
from dataclasses import dataclass, field

from . import disks

KIND_DISKS = "disks"
KIND_GROUPS = "groups"

# Normalised header names (see _key) accepted for each value.
DISK_COLUMNS = {
    "location": ("location", "position", "pos", "disklocation", "drivelocation", "encslot", "enclosureslot"),
    "enclosure": ("enclosure", "enclosureid", "encl", "shelf", "shelfid", "enclosurenumber"),
    "slot": ("slot", "slotnumber", "slotid", "bay", "baynumber", "drivebay"),
    "serial": ("serialnumber", "serial", "sn", "serialno", "diskserialnumber"),
    "size": ("size", "capacity", "totalsize", "disksize"),
    "type": ("type", "disktype", "drivetype", "interface", "mediatype"),
    "usage": ("usage", "role", "diskusage"),
    "disk_group": ("diskgroup", "diskgroupname", "group", "vdisk", "vdiskname"),
    "health": ("health", "healthstatus"),
    "manufacturer": ("manufacturer", "vendor", "make"),
    "model": ("model", "modelnumber", "productid", "partnumber"),
    "firmware": ("revision", "firmware", "firmwarerevision", "fwrevision", "fw", "firmwareversion"),
    "rpm": ("rmin", "rpm", "speed", "rotationalspeed", "speedrpm"),
    "power_on_hours": ("poweronhours", "poh", "poweronhrs", "hourspoweredon"),
}
GROUP_COLUMNS = {
    "name": ("name", "diskgroup", "diskgroupname", "vdisk", "vdiskname", "groupname"),
    "level": ("raidlevel", "raid", "level", "raidtype"),
    "pool": ("pool", "poolname"),
    "size": ("totalsize", "size", "capacity"),
    "disks": ("disks", "diskcount", "numberofdisks", "numdisks", "drives"),
    "health": ("health", "healthstatus"),
    "disk_type": ("disktype", "type"),
}

# Usage values of hot spares; "dedicated" spares belong to one disk group.
SPARE_USAGES = ("globalsp", "dedicatedsp", "spare", "globalspare", "dedicatedspare", "hotspare")
# Health values which mean the disk has failed.
FAILED_HEALTH = ("fault", "failed", "error")
# Disk group values without a real group.
NO_GROUP = ("", "-", "n/a", "none")

_LOCATION_PATTERN = re.compile(r"(\d+)\D+(\d+)")


@dataclass
class MSADisk:
    enclosure: str
    slot: int
    status: str
    disk_type: str = ""
    interface: str = ""
    capacity_gb: int | None = None
    disk_group: str = ""
    serial: str = ""
    manufacturer: str = ""
    model: str = ""
    firmware: str = ""
    power_on_hours: int | None = None
    usage: str = ""
    health: str = ""


@dataclass
class MSAGroup:
    name: str
    level: str
    level_text: str = ""
    pool: str = ""
    size: str = ""
    disk_count: int | None = None
    health: str = ""

    @property
    def description(self):
        parts = [
            f"Pool {self.pool}" if self.pool else "",
            self.size,
            f"{self.disk_count} Datenträger" if self.disk_count else "",
        ]
        return ", ".join(part for part in parts if part)


@dataclass
class MSAExport:
    kind: str = KIND_DISKS
    disks: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def enclosures(self):
        """Enclosure IDs in natural order with their disks."""
        result = {}
        for disk in sorted(self.disks, key=lambda item: (_natural(item.enclosure), item.slot)):
            result.setdefault(disk.enclosure, []).append(disk)
        return result

    @property
    def is_empty(self):
        return not self.disks and not self.groups


def _natural(value):
    return (0, int(value), "") if str(value).isdigit() else (1, 0, str(value))


def _key(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold())


def decode(data):
    if isinstance(data, bytes):
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
    return str(data or "").lstrip("﻿")


def _int(value):
    try:
        return int(str(value).strip().replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _read(text):
    """Return (rows, header lookup) for CSV text with ',', ';' or tab as delimiter."""
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return reader, {_key(name): name for name in (reader.fieldnames or []) if name}


def _resolve(headers, columns):
    """Map each value name to the header present in the file, or None."""
    return {
        name: next((headers[alias] for alias in aliases if alias in headers), None) for name, aliases in columns.items()
    }


def detect_kind(text):
    """KIND_DISKS, KIND_GROUPS or None, judged from the header line only."""
    text = decode(text).strip()
    if not text:
        return None
    _, headers = _read(text.splitlines()[0])
    disk_columns = _resolve(headers, DISK_COLUMNS)
    if disk_columns["location"] or (disk_columns["enclosure"] and disk_columns["slot"]):
        return KIND_DISKS
    group_columns = _resolve(headers, GROUP_COLUMNS)
    if group_columns["name"] and group_columns["level"]:
        return KIND_GROUPS
    return None


def looks_like_export(text):
    return detect_kind(text) is not None


def parse_location(text):
    """'1.4', '1:4', '1/4', '1-4' or 'Enclosure 1 Slot 4' → ('1', 4); None if unreadable."""
    match = _LOCATION_PATTERN.search(text or "")
    if not match:
        return None
    return str(int(match.group(1))), int(match.group(2))


def map_type(value, rpm=""):
    """Translate the MSA "Type" column, e.g. "SSD SAS", "SAS", "SAS MDL" or "SATA", into (type, interface)."""
    text = (value or "").upper()
    interface = "sata" if "SATA" in text else "sas" if "SAS" in text else "nvme" if "NVME" in text else ""
    if "SSD" in text or "NVME" in text or text.startswith("SSAS"):
        disk_type = "ssd" if interface != "nvme" else "nvme"
    elif text or (rpm and rpm.strip().lower() not in ("0k", "0")):
        disk_type = "hdd"
    else:
        disk_type = ""
    return disk_type, interface


def map_status(usage, health):
    if _key(health) in FAILED_HEALTH:
        return disks.STATUS_FAILED
    if _key(usage) in SPARE_USAGES:
        return disks.STATUS_SPARE
    return disks.STATUS_ACTIVE


def map_raid_level(text):
    """'RAID10', 'RAID-5', 'raid 6', 'R5', 'NRAID' or 'ADAPT' → a RAID_LEVELS key ("other" if unknown)."""
    key = _key(text)
    if re.fullmatch(r"r\d+", key):
        key = "raid" + key[1:]
    if key in ("nraid", "jbod", "none", "single"):
        return "jbod"
    if key == "raid1e":
        return "raid1"
    return key if key in disks.RAID_LEVELS else "other"


def parse_export(data):
    """Parse a disk or disk group export; rows that cannot be read end up in errors."""
    text = decode(data).strip()
    export = MSAExport()
    if not text:
        export.errors.append("Die Datei ist leer.")
        return export
    kind = detect_kind(text)
    if kind == KIND_GROUPS:
        export.kind = KIND_GROUPS
        _parse_groups(text, export)
    elif kind == KIND_DISKS:
        _parse_disks(text, export)
    else:
        export.errors.append(
            "Unbekanntes Format. Erwartet wird der Datenträger-Export (Spalte „Location“ bzw. „Enclosure“ und "
            "„Slot“) oder der Disk-Group-Export (Spalten „Name“ und „RAID Level“) einer HPE MSA."
        )
    if export.is_empty and not export.errors:
        export.errors.append("Die Datei enthält keine Einträge.")
    return export


def _parse_disks(text, export):
    reader, headers = _read(text)
    columns = _resolve(headers, DISK_COLUMNS)

    def column(row, name):
        key = columns[name]
        return (row.get(key) or "").strip() if key else ""

    seen = set()
    for line, row in enumerate(reader, start=2):
        if columns["location"]:
            location = column(row, "location")
        else:
            location = f"{column(row, 'enclosure')}.{column(row, 'slot')}".strip(".")
        if not location:
            continue
        position = parse_location(location)
        if position is None:
            export.errors.append(f"Zeile {line}: ungültige Position {location!r} (erwartet z. B. 1.4).")
            continue
        if position in seen:
            export.errors.append(f"Zeile {line}: Position {location} kommt mehrfach vor.")
            continue
        seen.add(position)

        try:
            capacity = disks.parse_capacity(column(row, "size")) if column(row, "size") else None
        except ValueError:
            capacity = None
        disk_type, interface = map_type(column(row, "type"), column(row, "rpm"))
        group = column(row, "disk_group")
        usage, health = column(row, "usage"), column(row, "health")
        hours = column(row, "power_on_hours")
        export.disks.append(
            MSADisk(
                enclosure=position[0],
                slot=position[1],
                status=map_status(usage, health),
                disk_type=disk_type,
                interface=interface,
                capacity_gb=capacity,
                disk_group="" if group.casefold() in NO_GROUP else group,
                serial=column(row, "serial"),
                manufacturer=column(row, "manufacturer"),
                model=column(row, "model"),
                firmware=column(row, "firmware"),
                power_on_hours=_int(hours) if hours else None,
                usage=usage,
                health=health,
            )
        )


def _parse_groups(text, export):
    reader, headers = _read(text)
    columns = _resolve(headers, GROUP_COLUMNS)

    def column(row, name):
        key = columns[name]
        return (row.get(key) or "").strip() if key else ""

    seen = set()
    for line, row in enumerate(reader, start=2):
        name = column(row, "name")
        if not name:
            continue
        if name.casefold() in seen:
            export.errors.append(f"Zeile {line}: Disk Group {name} kommt mehrfach vor.")
            continue
        seen.add(name.casefold())
        level_text = column(row, "level")
        count = column(row, "disks")
        export.groups.append(
            MSAGroup(
                name=name,
                level=map_raid_level(level_text),
                level_text=level_text,
                pool=column(row, "pool"),
                size=column(row, "size"),
                disk_count=_int(count) if count else None,
                health=column(row, "health"),
            )
        )


def suggest_slot_count(highest_slot):
    """Common MSA enclosure sizes: 12 LFF or 24 SFF bays; anything bigger is taken as is."""
    for size in (12, 24):
        if highest_slot <= size:
            return size
    return highest_slot


def suggest_form_factor(slot_count):
    return "3.5" if slot_count == 12 else "2.5" if slot_count == 24 else ""


ACTION_NEW = "new"
ACTION_UPDATE = "update"
ACTION_REPLACE = "replace"
ACTION_SKIP = "skip"
ACTION_CONFLICT = "conflict"

ACTION_LABELS = {
    ACTION_NEW: ("Neu", "success"),
    ACTION_UPDATE: ("Aktualisieren", "info"),
    ACTION_REPLACE: ("Ersetzt vorhandenen", "warning"),
    ACTION_SKIP: ("Übersprungen", "secondary"),
    ACTION_CONFLICT: ("Konflikt", "danger"),
}


def classify(disk, first_slot, last_slot, occupant_serial=None, serial_elsewhere=None, replace=False):
    """Decide what happens to one exported disk; returns (action, reason).

    occupant_serial: serial of the disk currently in the target slot ("" if it has none,
    None if the slot is free). serial_elsewhere: label of another slot that already
    holds this serial, if any.
    """
    if not first_slot <= disk.slot <= last_slot:
        return ACTION_CONFLICT, f"Steckplatz {disk.slot} liegt außerhalb des Bereichs ({first_slot}–{last_slot})."
    if disk.serial and serial_elsewhere:
        return ACTION_CONFLICT, f"Seriennummer steckt laut NetBox bereits in {serial_elsewhere}."
    if occupant_serial is None:
        return ACTION_NEW, ""
    if disk.serial and occupant_serial.casefold() == disk.serial.casefold():
        return ACTION_UPDATE, ""
    if replace:
        return (
            ACTION_REPLACE,
            f"Bisheriger Datenträger {occupant_serial or '(ohne Seriennummer)'} wird als ausgebaut markiert.",
        )
    return ACTION_SKIP, f"Steckplatz ist mit {occupant_serial or 'einem Datenträger ohne Seriennummer'} belegt."
