"""Pure helpers for importing the disk export of an HPE MSA (Pools → Disks → "Export to CSV")."""

import csv
import io
from dataclasses import dataclass, field

from . import disks

# Header names of the MSA export, casefolded.
COLUMN_LOCATION = "location"
REQUIRED_COLUMNS = (COLUMN_LOCATION,)

# Usage values of hot spares; "dedicated" spares belong to one disk group.
SPARE_USAGES = ("global sp", "dedicated sp", "spare")
# Health values which mean the disk has failed.
FAILED_HEALTH = ("fault", "failed")
# Disk group values without a real group.
NO_GROUP = ("", "-", "n/a")


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
class MSAExport:
    disks: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def enclosures(self):
        """Enclosure IDs in natural order with their disks."""
        result = {}
        for disk in sorted(self.disks, key=lambda item: (_natural(item.enclosure), item.slot)):
            result.setdefault(disk.enclosure, []).append(disk)
        return result


def _natural(value):
    return (0, int(value), "") if str(value).isdigit() else (1, 0, str(value))


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


def looks_like_export(text):
    """True if the first line carries the MSA columns "Location" and "Serial Number"."""
    first_line = (text or "").lstrip("\ufeff").split("\n", 1)[0].casefold()
    return COLUMN_LOCATION in first_line and "serial number" in first_line


def map_type(value, rpm=""):
    """Translate the MSA "Type" column, e.g. "SSD SAS", "SAS", "SAS MDL" or "SATA", into (type, interface)."""
    text = (value or "").upper()
    interface = "sata" if "SATA" in text else "sas" if "SAS" in text else "nvme" if "NVME" in text else ""
    if "SSD" in text or "NVME" in text:
        disk_type = "ssd" if interface != "nvme" else "nvme"
    elif text or (rpm and rpm.strip().lower() not in ("0k", "0")):
        disk_type = "hdd"
    else:
        disk_type = ""
    return disk_type, interface


def map_status(usage, health):
    if (health or "").strip().casefold() in FAILED_HEALTH:
        return disks.STATUS_FAILED
    if (usage or "").strip().casefold() in SPARE_USAGES:
        return disks.STATUS_SPARE
    return disks.STATUS_ACTIVE


def parse_export(data):
    """Parse the CSV export into an MSAExport; rows that cannot be read end up in errors."""
    text = decode(data).strip()
    export = MSAExport()
    if not text:
        export.errors.append("Die Datei ist leer.")
        return export
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = {name.strip().casefold(): name for name in (reader.fieldnames or [])}
    missing = [name for name in REQUIRED_COLUMNS if name not in headers]
    if missing:
        export.errors.append("Das ist kein HPE-MSA-Datenträger-Export: die Spalte „Location“ fehlt.")
        return export

    def column(row, name):
        key = headers.get(name)
        return (row.get(key) or "").strip() if key else ""

    seen = set()
    for line, row in enumerate(reader, start=2):
        location = column(row, COLUMN_LOCATION)
        if not location:
            continue
        enclosure, _, slot_text = location.partition(".")
        slot = _int(slot_text)
        if not enclosure or slot is None:
            export.errors.append(f"Zeile {line}: ungültige Position {location!r} (erwartet z. B. 1.4).")
            continue
        if (enclosure, slot) in seen:
            export.errors.append(f"Zeile {line}: Position {location} kommt mehrfach vor.")
            continue
        seen.add((enclosure, slot))

        try:
            capacity = disks.parse_capacity(column(row, "size")) if column(row, "size") else None
        except ValueError:
            capacity = None
        disk_type, interface = map_type(column(row, "type"), column(row, "r/min"))
        group = column(row, "disk group")
        usage, health = column(row, "usage"), column(row, "health")
        export.disks.append(
            MSADisk(
                enclosure=enclosure,
                slot=slot,
                status=map_status(usage, health),
                disk_type=disk_type,
                interface=interface,
                capacity_gb=capacity,
                disk_group="" if group.casefold() in NO_GROUP else group,
                serial=column(row, "serial number"),
                manufacturer=column(row, "manufacturer"),
                model=column(row, "model"),
                firmware=column(row, "revision"),
                power_on_hours=_int(column(row, "power on hours")) if column(row, "power on hours") else None,
                usage=usage,
                health=health,
            )
        )
    if not export.disks and not export.errors:
        export.errors.append("Die Datei enthält keine Datenträger.")
    return export


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
