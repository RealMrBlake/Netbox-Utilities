import django_tables2 as tables
from django.db.models.signals import post_save

COLUMN_NAME = "netbox_utilities_disks"


def sync_disk_tenants(sender, instance, raw=False, **kwargs):
    """Keep the tenant of all disks in line with their device."""
    if raw or not instance.pk:
        return
    from .models import Disk

    Disk.objects.filter(device_id=instance.pk).exclude(tenant_id=instance.tenant_id).update(
        tenant_id=instance.tenant_id
    )


class DeviceDisksColumn(tables.Column):
    """Shows used/total slots for devices with a disk layout, linked to the tab."""

    @staticmethod
    def occupancy(record):
        from . import disks
        from .models import Disk, DiskBayLayout

        layout = DiskBayLayout.objects.filter(device=record).only("slot_count").first()
        if layout is None:
            return None
        used = Disk.objects.filter(device=record, status__in=disks.SLOT_OCCUPYING_STATUSES).count()
        return f"{used}/{layout.slot_count}"

    def render(self, record):
        from django.urls import reverse
        from django.utils.html import format_html

        occupancy = self.occupancy(record)
        if occupancy is None:
            return "—"
        return format_html('<a href="{}">{}</a>', reverse("dcim:device_disks", kwargs={"pk": record.pk}), occupancy)

    def value(self, record):
        return self.occupancy(record) or ""


def install_disk_support():
    from dcim.models import Device
    from dcim.tables import DeviceTable
    from utilities.tables import register_table_column

    # Registers the "Datenträger" device tab before NetBox builds the dcim URLs.
    from . import disk_views  # noqa: F401

    post_save.connect(
        sync_disk_tenants,
        sender=Device,
        dispatch_uid="netbox_utilities.sync_disk_tenants",
        weak=False,
    )
    register_table_column(
        DeviceDisksColumn(accessor=tables.A("pk"), verbose_name="Datenträger", orderable=False, empty_values=()),
        COLUMN_NAME,
        DeviceTable,
    )
