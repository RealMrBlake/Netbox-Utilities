import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from . import hardware
from .models import CPUModel, DeviceHardware


class ClockColumn(tables.Column):
    def render(self, value):
        return hardware.format_clock(value)


class MemoryColumn(tables.Column):
    def render(self, value):
        return hardware.format_memory(value)


class CPUModelTable(NetBoxTable):
    name = tables.Column(linkify=True, verbose_name="Modell")
    manufacturer = columns.ChoiceFieldColumn(verbose_name="Hersteller")
    family = tables.Column(verbose_name="Familie")
    cores = tables.Column(verbose_name="Kerne")
    threads = tables.Column(verbose_name="Threads")
    base_clock_ghz = ClockColumn(verbose_name="Basistakt")
    boost_clock_ghz = ClockColumn(verbose_name="Turbo")
    tdp_watts = tables.Column(verbose_name="TDP (W)")
    socket = tables.Column(verbose_name="Sockel")
    launch_year = tables.Column(verbose_name="Jahr")
    max_sockets = tables.Column(verbose_name="Max. Sockel")
    builtin = columns.BooleanColumn(verbose_name="Katalog")
    device_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_utilities:devicehardware_list",
        url_params={"cpu_id": "pk"},
        verbose_name="Geräte",
    )
    tags = columns.TagColumn(url_name="plugins:netbox_utilities:cpumodel_list")

    class Meta(NetBoxTable.Meta):
        model = CPUModel
        fields = (
            "pk",
            "id",
            "name",
            "manufacturer",
            "family",
            "cores",
            "threads",
            "base_clock_ghz",
            "boost_clock_ghz",
            "tdp_watts",
            "socket",
            "launch_year",
            "max_sockets",
            "builtin",
            "device_count",
            "description",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "name",
            "family",
            "cores",
            "threads",
            "base_clock_ghz",
            "boost_clock_ghz",
            "socket",
            "launch_year",
            "device_count",
        )


class DeviceHardwareTable(NetBoxTable):
    device = tables.Column(linkify=True, verbose_name="Gerät")
    cluster = tables.Column(accessor=tables.A("device__cluster"), linkify=True, verbose_name="Cluster")
    cpu = tables.Column(linkify=True, verbose_name="CPU-Modell")
    cpu_count = tables.Column(verbose_name="CPUs")
    total_cores = tables.Column(verbose_name="Kerne", orderable=False)
    total_threads = tables.Column(verbose_name="Threads", orderable=False)
    memory_gb = MemoryColumn(verbose_name="RAM")
    memory_type = columns.ChoiceFieldColumn(verbose_name="RAM-Typ")
    memory_detail = tables.Column(verbose_name="Bestückung", orderable=False)
    comments = columns.MarkdownColumn()
    tags = columns.TagColumn(url_name="plugins:netbox_utilities:devicehardware_list")

    class Meta(NetBoxTable.Meta):
        model = DeviceHardware
        fields = (
            "pk",
            "id",
            "device",
            "cluster",
            "cpu",
            "cpu_count",
            "total_cores",
            "total_threads",
            "memory_gb",
            "memory_type",
            "memory_modules",
            "memory_module_gb",
            "memory_speed_mts",
            "memory_detail",
            "description",
            "comments",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "device",
            "cluster",
            "cpu",
            "cpu_count",
            "total_cores",
            "total_threads",
            "memory_gb",
            "memory_detail",
        )
