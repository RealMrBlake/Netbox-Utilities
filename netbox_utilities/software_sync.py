"""
Transfer the software list of inventory reports in device comments into netbox-slm.

Two writers put a software list into the comments of a client device:

* the NetBox Windows Agent (mode ``netbox``)::

      ## Installed software (2)
      - 7-Zip 23.01 (x64) 23.01 — Igor Pavlov
      - Mozilla Firefox (x64 de) 120.0 — Mozilla

* the NetBox Synchronizer desktop app (agent scan in mode ``listen``)::

      ### Installierte Software (2)

      | Programm | Version | Hersteller |
      |---|---|---|
      | 7-Zip 23.01 (x64) | 23.01 | Igor Pavlov |

On every device save the installations recorded this way are brought in line with the report.
Installations entered by hand are never changed or removed.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Marks installations created from a report; only these are removed again when a report drops them.
SYNC_MARKER = "Automatisch aus dem Inventarbericht übernommen (netbox-utilities)."
UNKNOWN_VERSION = "unbekannt"

_HEADING = re.compile(r"^\s*#{1,6}\s*(installed software|installierte software)\b", re.IGNORECASE)
_ANY_HEADING = re.compile(r"^\s*#{1,6}\s")
# At least one dot, so a year in a product name ("Office 2024") is not taken for a version.
_VERSION = re.compile(r"^v?\d+(?:\.\w+)+(?:[\-_+]\w+)*$", re.IGNORECASE)
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{2,}")


@dataclass(frozen=True)
class SoftwareEntry:
    name: str
    version: str
    publisher: str = ""

    @property
    def key(self):
        return self.name.casefold(), self.version.casefold()


def has_software_report(comments):
    return any(_HEADING.match(line) for line in str(comments or "").splitlines())


def _software_lines(comments):
    """Lines of the first software section, up to the next heading."""
    inside = False
    for line in str(comments or "").splitlines():
        if _HEADING.match(line):
            if inside:
                return
            inside = True
            continue
        if inside:
            if _ANY_HEADING.match(line) or line.strip().startswith("<!--"):
                return
            yield line.strip()


def _parse_table_row(line):
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) < 2 or _TABLE_SEPARATOR.match(line) or cells[0].casefold() in {"programm", "name", "software"}:
        return None
    return cells[0], cells[1], cells[2] if len(cells) > 2 else ""


def _parse_bullet(line):
    """``- Name Version — Publisher``: the version is the last word if it looks like one."""
    text = line[1:].strip()
    publisher = ""
    if " — " in text:
        text, publisher = (part.strip() for part in text.rsplit(" — ", 1))
    words = text.rsplit(" ", 1)
    if len(words) == 2 and _VERSION.match(words[1]):
        return words[0], words[1], publisher
    return text, "", publisher


def clean_name(name, version):
    """Remove a version the vendor appended to the product name ("Foo 1.2", "Foo - 1.2.3")."""
    name = " ".join(str(name or "").split())
    version = str(version or "").strip()
    if not version:
        return name
    match = re.match(r"^(?P<base>.+?)\s*(?:-\s*)?v?(?P<tail>\d[\w.\-+]*)$", name)
    if match:
        tail = match.group("tail")
        if version.startswith(tail) or tail.startswith(version):
            return match.group("base").rstrip(" -")
    return name


def parse_software_report(comments):
    """Software entries of a report in device comments; an empty list without a report."""
    entries = {}
    for line in _software_lines(comments):
        if line.startswith("|"):
            parsed = _parse_table_row(line)
        elif line.startswith(("- ", "* ")):
            parsed = _parse_bullet(line)
        else:
            parsed = None
        if not parsed or not parsed[0].strip():
            continue
        raw_name, version, publisher = (" ".join(str(part or "").split()) for part in parsed)
        version = version or UNKNOWN_VERSION
        entry = SoftwareEntry(clean_name(raw_name, version)[:128], version[:64], publisher[:255])
        entries.setdefault(entry.key, entry)
    return list(entries.values())


def _product_for(entry, products, manufacturers):
    from netbox_slm.models import SoftwareProduct

    key = entry.name.casefold()
    product = products.get(key)
    if product is None:
        product = SoftwareProduct.objects.filter(name__iexact=entry.name).order_by("pk").first()
        if product is None:
            product = SoftwareProduct(name=entry.name, manufacturer=manufacturers.get(entry.publisher.casefold()))
            if product.manufacturer is None and entry.publisher:
                product.description = entry.publisher
            product.full_clean()
            product.save()
        products[key] = product
    return product


def _version_for(product, entry, versions):
    from netbox_slm.models import SoftwareProductVersion

    key = (product.pk, entry.version.casefold())
    version = versions.get(key)
    if version is None:
        version = (
            SoftwareProductVersion.objects.filter(software_product=product, name__iexact=entry.version)
            .order_by("pk")
            .first()
        )
        if version is None:
            version = SoftwareProductVersion(software_product=product, name=entry.version)
            version.full_clean()
            version.save()
        versions[key] = version
    return version


def sync_device_software(device):
    """
    Bring the netbox-slm installations of a device in line with the report in its comments.

    Returns (created, removed). Devices without a report are left untouched, so removing the
    report by hand does not delete anything.
    """
    from dcim.models import Manufacturer
    from django.db import transaction
    from netbox_slm.models import SoftwareProductInstallation

    comments = getattr(device, "comments", "")
    if not has_software_report(comments):
        return 0, 0
    entries = parse_software_report(comments)
    manufacturers = {
        manufacturer.name.casefold(): manufacturer
        for manufacturer in Manufacturer.objects.filter(
            name__in={entry.publisher for entry in entries if entry.publisher}
        )
    }

    with transaction.atomic():
        existing = SoftwareProductInstallation.objects.filter(device=device).select_related(
            "software_product", "version"
        )
        present = {}
        for installation in existing:
            key = (installation.software_product.name.casefold(), installation.version.name.casefold())
            present.setdefault(key, installation)

        wanted = {entry.key: entry for entry in entries}
        products, versions, created = {}, {}, 0
        for key, entry in wanted.items():
            if key in present:
                continue
            product = _product_for(entry, products, manufacturers)
            version = _version_for(product, entry, versions)
            SoftwareProductInstallation.objects.create(
                device=device, software_product=product, version=version, comments=SYNC_MARKER
            )
            created += 1

        stale = [
            installation.pk
            for key, installation in present.items()
            if key not in wanted and installation.comments == SYNC_MARKER
        ]
        removed = SoftwareProductInstallation.objects.filter(pk__in=stale).delete()[0] if stale else 0
    return created, removed


def _sync_after_save(sender, instance, raw=False, **kwargs):
    if raw or not has_software_report(getattr(instance, "comments", "")):
        return
    try:
        sync_device_software(instance)
    except Exception:  # noqa: BLE001 - a broken report must never block saving the device
        logger.exception("Software of device %s could not be transferred to netbox-slm", instance.pk)


def remove_synced_installations(device):
    """netbox-slm protects devices with installations; the automatic ones go with the device."""
    from netbox_slm.models import SoftwareProductInstallation

    return SoftwareProductInstallation.objects.filter(device=device, comments=SYNC_MARKER).delete()[0]


def install_software_sync():
    from dcim.models import Device
    from django.db.models.signals import post_save

    post_save.connect(_sync_after_save, sender=Device, dispatch_uid=f"{__name__}.device")

    if getattr(Device.delete, "_netbox_utilities_software", False):
        return
    original_delete = Device.delete

    def delete(self, *args, **kwargs):
        if self.pk:
            remove_synced_installations(self)
        return original_delete(self, *args, **kwargs)

    delete._netbox_utilities_software = True
    Device.delete = delete
