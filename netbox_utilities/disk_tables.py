import django_tables2 as tables
from django.utils.html import format_html, format_html_join
from netbox.tables import NetBoxTable, columns

from .models import Disk, DiskBayTemplate, RAIDGroup


class CapacityColumn(tables.Column):
    def render(self, value):
        from .disks import format_capacity

        return format_capacity(value)


class DiskWarningsColumn(tables.Column):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("accessor", tables.A("pk"))
        kwargs.setdefault("orderable", False)
        kwargs.setdefault("verbose_name", "Warnungen")
        kwargs.setdefault("empty_values", ())
        super().__init__(*args, **kwargs)

    def render(self, record):
        warnings = record.warnings
        if not warnings:
            return "—"
        return format_html_join(
            " ", '<span class="badge text-bg-{}">{}</span>', ((level, text) for level, text in warnings)
        )

    def value(self, record):
        return "; ".join(text for _, text in record.warnings)


class DiskTable(NetBoxTable):
    device = tables.Column(linkify=True, verbose_name="Gerät")
    bay = tables.Column(accessor=tables.A("bay__name"), verbose_name="Bereich")
    slot = tables.Column(linkify=True, verbose_name="Slot")
    status = columns.ChoiceFieldColumn(verbose_name="Status")
    disk_type = columns.ChoiceFieldColumn(verbose_name="Typ")
    interface = columns.ChoiceFieldColumn(verbose_name="Schnittstelle")
    form_factor = columns.ChoiceFieldColumn(verbose_name="Bauform")
    capacity_gb = CapacityColumn(verbose_name="Größe")
    serial = tables.Column(linkify=True, verbose_name="Seriennummer")
    raid_group = tables.Column(linkify=True, verbose_name="RAID-Gruppe")
    tenant = tables.Column(linkify=True, verbose_name="Mandant")
    warnings = DiskWarningsColumn()
    comments = columns.MarkdownColumn()
    tags = columns.TagColumn(url_name="plugins:netbox_utilities:disk_list")

    class Meta(NetBoxTable.Meta):
        model = Disk
        fields = (
            "pk",
            "id",
            "device",
            "bay",
            "slot",
            "status",
            "disk_type",
            "interface",
            "form_factor",
            "manufacturer",
            "model",
            "capacity_gb",
            "serial",
            "firmware",
            "manufacture_date",
            "install_date",
            "removal_date",
            "warranty_end",
            "raid_group",
            "tenant",
            "warnings",
            "description",
            "comments",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "pk",
            "device",
            "bay",
            "slot",
            "status",
            "disk_type",
            "manufacturer",
            "model",
            "capacity_gb",
            "serial",
            "warranty_end",
            "tenant",
            "warnings",
        )


class DeviceDiskHistoryTable(NetBoxTable):
    """Removed and replaced disks on the device tab."""

    bay = tables.Column(accessor=tables.A("bay__name"), verbose_name="Bereich")
    slot = tables.Column(verbose_name="Slot")
    serial = tables.Column(linkify=True, verbose_name="Seriennummer")
    capacity_gb = CapacityColumn(verbose_name="Größe")
    actions = columns.ActionsColumn(actions=("edit", "delete"))

    class Meta(NetBoxTable.Meta):
        model = Disk
        fields = (
            "bay",
            "slot",
            "manufacturer",
            "model",
            "capacity_gb",
            "serial",
            "install_date",
            "removal_date",
            "description",
            "actions",
        )
        default_columns = fields


class RAIDGroupTable(NetBoxTable):
    name = tables.Column(linkify=True, verbose_name="Name")
    device = tables.Column(linkify=True, verbose_name="Gerät")
    level = columns.ChoiceFieldColumn(verbose_name="RAID-Level")
    member_count = tables.Column(verbose_name="Mitglieder", accessor=tables.A("pk"), orderable=False)
    usable_capacity = tables.Column(
        verbose_name="Nutzkapazität", accessor=tables.A("pk"), orderable=False, empty_values=()
    )
    state = tables.Column(verbose_name="Zustand", accessor=tables.A("pk"), orderable=False, empty_values=())
    tags = columns.TagColumn(url_name="plugins:netbox_utilities:raidgroup_list")

    class Meta(NetBoxTable.Meta):
        model = RAIDGroup
        fields = (
            "pk",
            "id",
            "name",
            "device",
            "level",
            "spans",
            "member_count",
            "usable_capacity",
            "state",
            "description",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = ("pk", "name", "device", "level", "member_count", "usable_capacity", "state")

    def render_member_count(self, record):
        return f"{len(record.members)} + {len(record.hot_spares)} Spare" if record.hot_spares else len(record.members)

    def render_usable_capacity(self, record):
        usable, _, error = record.capacity
        return error or (record.usable_capacity_display if usable else "—")

    def render_state(self, record):
        if record.is_degraded:
            return format_html('<span class="badge text-bg-{}">{}</span>', "danger", "Degradiert")
        if record.capacity[2]:
            return format_html('<span class="badge text-bg-{}">{}</span>', "warning", "Unvollständig")
        return format_html('<span class="badge text-bg-{}">{}</span>', "success", "OK")


class DiskBayTemplateTable(NetBoxTable):
    device_type = tables.Column(linkify=True, verbose_name="Gerätetyp")
    name = tables.Column(linkify=True, verbose_name="Bereich")
    numbering = columns.ChoiceFieldColumn(verbose_name="Nummerierung")
    form_factor = columns.ChoiceFieldColumn(verbose_name="Bauform")

    class Meta(NetBoxTable.Meta):
        model = DiskBayTemplate
        fields = (
            "pk",
            "id",
            "device_type",
            "name",
            "weight",
            "slot_count",
            "rows",
            "first_slot",
            "numbering",
            "form_factor",
            "created",
            "last_updated",
        )
        default_columns = ("pk", "device_type", "name", "slot_count", "rows", "first_slot", "numbering", "form_factor")
