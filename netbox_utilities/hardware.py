"""Pure helpers for "CPU & RAM": capacity of hosts and clusters versus the virtual machines on them."""

from dataclasses import dataclass, field
from decimal import Decimal

DEFAULT_HARDWARE_DEVICE_ROLES = ("Server",)
# vCPUs per physical core above which the cluster is shown as overcommitted.
DEFAULT_VCPU_RATIO_WARNING = 4

# VM states that do not use host resources.
INACTIVE_VM_STATUSES = ("offline", "decommissioning")

MEMORY_TYPES = {
    "ddr3": "DDR3",
    "ddr4": "DDR4",
    "ddr5": "DDR5",
    "other": "Sonstiges",
}


def configured_roles(roles=None):
    if roles is None:
        try:
            from netbox.plugins import get_plugin_config

            roles = get_plugin_config("netbox_utilities", "hardware_device_roles")
        except Exception:  # noqa: BLE001 - outside NetBox (tests) fall back to defaults
            roles = None
    return {str(role).casefold() for role in (roles if roles is not None else DEFAULT_HARDWARE_DEVICE_ROLES)}


def supports_hardware(device, roles=None):
    """Servers by role, and every device that is a host of a virtualization cluster."""
    if getattr(device, "cluster_id", None):
        return True
    role = getattr(device, "role", None)
    return bool(role and str(getattr(role, "name", "")).casefold() in configured_roles(roles))


def vcpu_ratio_warning():
    try:
        from netbox.plugins import get_plugin_config

        return get_plugin_config("netbox_utilities", "hardware_vcpu_ratio_warning")
    except Exception:  # noqa: BLE001
        return DEFAULT_VCPU_RATIO_WARNING


def format_memory(gigabytes):
    """RAM as vendors label it: 768 GB, 1,5 TB."""
    if gigabytes in (None, ""):
        return "—"
    gigabytes = Decimal(str(gigabytes))
    if gigabytes >= 1024:
        text = f"{gigabytes / 1024:.2f}".rstrip("0").rstrip(".")
        return f"{text} TB".replace(".", ",")
    text = f"{gigabytes:.1f}".rstrip("0").rstrip(".")
    return f"{text} GB".replace(".", ",")


def format_clock(ghz):
    if ghz in (None, ""):
        return "—"
    text = f"{Decimal(str(ghz)):.2f}".rstrip("0").rstrip(".")
    return f"{text} GHz".replace(".", ",")


def format_ratio(value):
    if value is None:
        return "—"
    return f"{value:.1f}".replace(".", ",") + " : 1"


def percent(part, whole):
    if not whole:
        return None
    return round(float(part) / float(whole) * 100)


@dataclass
class Host:
    """One physical host; cores/threads/memory are None when no hardware is recorded."""

    name: str
    cores: int | None = None
    threads: int | None = None
    memory_gb: float | None = None
    vcpus: float = 0
    vm_memory_gb: float = 0
    vm_count: int = 0

    @property
    def complete(self):
        return bool(self.cores and self.memory_gb)


@dataclass
class Capacity:
    hosts: list = field(default_factory=list)
    vm_count: int = 0
    vcpus: float = 0
    vm_memory_gb: float = 0
    unplaced_vm_count: int = 0

    @property
    def known_hosts(self):
        return [host for host in self.hosts if host.complete]

    @property
    def missing_hosts(self):
        return [host for host in self.hosts if not host.complete]

    @property
    def cores(self):
        return sum(host.cores or 0 for host in self.hosts)

    @property
    def threads(self):
        return sum(host.threads or 0 for host in self.hosts)

    @property
    def memory_gb(self):
        return sum(host.memory_gb or 0 for host in self.hosts)

    @property
    def vcpu_per_core(self):
        return self.vcpus / self.cores if self.cores else None

    @property
    def vcpu_per_thread(self):
        return self.vcpus / self.threads if self.threads else None

    @property
    def memory_percent(self):
        return percent(self.vm_memory_gb, self.memory_gb)

    @property
    def failover_memory_gb(self):
        """RAM left if the largest host fails (N+1); None with fewer than two known hosts."""
        known = self.known_hosts
        if len(known) < 2:
            return None
        return self.memory_gb - max(host.memory_gb for host in known)

    @property
    def failover_ok(self):
        reserve = self.failover_memory_gb
        return None if reserve is None else self.vm_memory_gb <= reserve

    def warnings(self, ratio_warning=DEFAULT_VCPU_RATIO_WARNING):
        """(level, text) tuples for the capacity panel."""
        result = []
        if self.missing_hosts:
            names = ", ".join(host.name for host in self.missing_hosts)
            result.append(("warning", f"CPU/RAM fehlt bei: {names}"))
        if self.memory_gb and self.vm_memory_gb > self.memory_gb:
            result.append(("danger", "Die VMs haben mehr RAM zugewiesen, als die Hosts haben."))
        elif self.failover_ok is False:
            result.append(("warning", "Fällt der größte Host aus, reicht der RAM nicht für alle VMs (N+1)."))
        ratio = self.vcpu_per_core
        if ratio_warning and ratio is not None and ratio > ratio_warning:
            result.append(("warning", f"Mehr als {ratio_warning} vCPUs pro physischem Kern."))
        return result


def build_capacity(hosts, vms):
    """Aggregate hosts and VMs.

    hosts: iterable of Host (memory in GB).
    vms:   iterable of (host name or None, vcpus, memory in MB, status).
    """
    capacity = Capacity(hosts=list(hosts))
    by_name = {host.name: host for host in capacity.hosts}
    for host_name, vcpus, memory_mb, status in vms:
        if status in INACTIVE_VM_STATUSES:
            continue
        vcpus = float(vcpus or 0)
        memory_gb = (memory_mb or 0) / 1024
        capacity.vm_count += 1
        capacity.vcpus += vcpus
        capacity.vm_memory_gb += memory_gb
        host = by_name.get(host_name)
        if host is None:
            capacity.unplaced_vm_count += 1
        else:
            host.vm_count += 1
            host.vcpus += vcpus
            host.vm_memory_gb += memory_gb
    return capacity
