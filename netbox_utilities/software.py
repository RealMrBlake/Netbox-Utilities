"""Pure helpers for the client software overview (data from the netbox-slm plugin)."""

import re
from dataclasses import dataclass, field
from datetime import date

DEFAULT_SOFTWARE_DEVICE_ROLES = ("Client", "Windows Client")
# Number of products in the "top products" chart.
TOP_PRODUCTS = 10


def configured_roles(roles=None):
    if roles is None:
        try:
            from netbox.plugins import get_plugin_config

            roles = get_plugin_config("netbox_utilities", "software_device_roles")
        except Exception:  # noqa: BLE001 - outside NetBox (tests) fall back to defaults
            roles = None
    return {str(role).casefold() for role in (roles if roles is not None else DEFAULT_SOFTWARE_DEVICE_ROLES)}


def is_client_role(role, roles=None):
    """A role counts as client role if its name or slug is configured ("Windows Client" or "windows-client")."""
    if role is None:
        return False
    configured = configured_roles(roles)
    slugs = {name.replace(" ", "-") for name in configured}
    return (
        str(getattr(role, "name", "")).casefold() in configured
        or str(getattr(role, "slug", "")).casefold() in configured | slugs
    )


def supports_software(device, roles=None):
    """Devices with a configured client role get the "Software" tab."""
    return is_client_role(getattr(device, "role", None), roles)


def version_key(name):
    """Natural sort key: "10.2" after "9.11", numbers before text, case-insensitive."""
    parts = re.split(r"(\d+)", str(name or "").casefold())
    return tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in parts if part)


def percent(part, total):
    return round(part * 100 / total) if total else 0


@dataclass
class VersionStats:
    id: int
    name: str
    end_of_support: date | None = None
    release_type: str = ""
    devices: set = field(default_factory=set)
    installations: int = 0
    # Share of the product's devices, and intensity in the version chart (newest = strongest)
    share: int = 0
    shade: int = 100

    @property
    def device_count(self):
        return len(self.devices)

    def support_expired(self, today=None):
        return bool(self.end_of_support and self.end_of_support < (today or date.today()))


@dataclass
class ProductStats:
    id: int
    name: str
    manufacturer: str = ""
    versions: dict = field(default_factory=dict)
    devices: set = field(default_factory=set)
    installations: int = 0
    share: int = 0
    bar: int = 0

    @property
    def device_count(self):
        return len(self.devices)

    @property
    def version_count(self):
        return len(self.versions)

    @property
    def versions_by_name(self):
        """Newest version first."""
        return sorted(self.versions.values(), key=lambda version: version_key(version.name), reverse=True)

    @property
    def latest_version(self):
        versions = self.versions_by_name
        return versions[0] if versions else None

    @property
    def expired_devices(self):
        return {device for version in self.versions.values() if version.support_expired() for device in version.devices}


@dataclass
class SoftwareSummary:
    products: list
    device_total: int
    devices_with_software: int
    installations: int
    version_count: int
    expired_device_count: int

    @property
    def devices_without_software(self):
        return max(self.device_total - self.devices_with_software, 0)

    @property
    def coverage(self):
        return percent(self.devices_with_software, self.device_total)

    @property
    def product_count(self):
        return len(self.products)

    @property
    def top_products(self):
        return self.products[:TOP_PRODUCTS]


def summarize(rows, device_total=None):
    """
    Aggregate installation rows into products and versions.

    Each row is a mapping with product_id, product_name, manufacturer, version_id, version_name,
    end_of_support, release_type and device_id. Devices are counted once per product/version, even
    if the same software was recorded twice on a device.
    """
    products = {}
    all_devices = set()
    installations = 0
    for row in rows:
        installations += 1
        product = products.get(row["product_id"])
        if product is None:
            product = products[row["product_id"]] = ProductStats(
                id=row["product_id"], name=row["product_name"], manufacturer=row.get("manufacturer") or ""
            )
        version = product.versions.get(row["version_id"])
        if version is None:
            version = product.versions[row["version_id"]] = VersionStats(
                id=row["version_id"],
                name=row["version_name"],
                end_of_support=row.get("end_of_support"),
                release_type=row.get("release_type") or "",
            )
        product.installations += 1
        version.installations += 1
        product.devices.add(row["device_id"])
        version.devices.add(row["device_id"])
        all_devices.add(row["device_id"])

    total = device_total if device_total is not None else len(all_devices)
    ordered = sorted(products.values(), key=lambda product: (-product.device_count, product.name.casefold()))
    most = ordered[0].device_count if ordered else 0
    for product in ordered:
        product.share = percent(product.device_count, total)
        product.bar = percent(product.device_count, most)
        versions = product.versions_by_name
        for index, version in enumerate(versions):
            version.share = percent(version.device_count, product.device_count)
            # Newest version at 100 %, older ones fade out to 35 %.
            version.shade = 100 - round(index * 65 / max(len(versions) - 1, 1))
    expired = {device for product in ordered for device in product.expired_devices}
    return SoftwareSummary(
        products=ordered,
        device_total=total,
        devices_with_software=len(all_devices),
        installations=installations,
        version_count=sum(product.version_count for product in ordered),
        expired_device_count=len(expired),
    )
