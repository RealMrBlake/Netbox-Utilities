import django_tables2 as tables


def _record(device):
    return getattr(device, "netbox_utilities_hardware", None)


class DeviceCPUColumn(tables.Column):
    def render(self, record):
        hardware = _record(record)
        return hardware.cpu_display if hardware and hardware.cpu_id else "—"

    def value(self, record):
        hardware = _record(record)
        return hardware.cpu_display if hardware and hardware.cpu_id else ""


class DeviceCoresColumn(tables.Column):
    def render(self, record):
        hardware = _record(record)
        if not hardware or not hardware.cpu_id:
            return "—"
        return f"{hardware.total_cores} / {hardware.total_threads}"

    def value(self, record):
        hardware = _record(record)
        return hardware.total_cores if hardware and hardware.cpu_id else ""


class DeviceMemoryColumn(tables.Column):
    def render(self, record):
        hardware = _record(record)
        return hardware.memory_display if hardware and hardware.memory_gb else "—"

    def value(self, record):
        hardware = _record(record)
        return hardware.memory_gb if hardware and hardware.memory_gb else ""


class ClusterCapacityColumn(tables.Column):
    """vCPU:core ratio and RAM allocation of a cluster, e.g. "3,2 : 1 · 74 %"."""

    @staticmethod
    def capacity(record):
        from dcim.models import Device
        from virtualization.models import VirtualMachine

        from .hardware import build_capacity
        from .hardware_views import host_entry, vm_rows

        hosts = Device.objects.filter(cluster=record).select_related("netbox_utilities_hardware__cpu")
        vms = VirtualMachine.objects.filter(cluster=record)
        return build_capacity([host_entry(device) for device in hosts], vm_rows(vms))

    def render(self, record):
        from .hardware import format_ratio

        capacity = self.capacity(record)
        if not capacity.cores:
            return "—"
        memory = f" · {capacity.memory_percent} % RAM" if capacity.memory_percent is not None else ""
        return f"{format_ratio(capacity.vcpu_per_core)}{memory}"

    def value(self, record):
        return self.render(record)


def install_hardware_support():
    from dcim.tables import DeviceTable
    from utilities.tables import register_table_column
    from virtualization.tables import ClusterTable

    # Registers the "CPU & RAM" device tab before NetBox builds the dcim URLs.
    from . import hardware_views  # noqa: F401

    common = {"accessor": tables.A("pk"), "orderable": False, "empty_values": ()}
    register_table_column(DeviceCPUColumn(verbose_name="CPU", **common), "netbox_utilities_cpu", DeviceTable)
    register_table_column(
        DeviceCoresColumn(verbose_name="Kerne / Threads", **common), "netbox_utilities_cores", DeviceTable
    )
    register_table_column(DeviceMemoryColumn(verbose_name="RAM", **common), "netbox_utilities_memory", DeviceTable)
    # Runs a few queries per row, so it is only shown when added under "Configure Table".
    register_table_column(
        ClusterCapacityColumn(verbose_name="vCPU : Kern · RAM", **common), "netbox_utilities_capacity", ClusterTable
    )
