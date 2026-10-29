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
    """One physical host; cores/threads/memory are None when no hardware is recorded.

    vcpus/vm_memory_gb come from VMs placed on this host, shared_* is its share of the
    cluster VMs without a fixed host (see build_capacity).
    """

    name: str
    cores: int | None = None
    threads: int | None = None
    memory_gb: float | None = None
    key: object = None
    vcpus: float = 0
    vm_memory_gb: float = 0
    vm_count: int = 0
    shared_vcpus: float = 0
    shared_memory_gb: float = 0

    def __post_init__(self):
        if self.key is None:
            self.key = self.name

    @property
    def complete(self):
        return bool(self.cores and self.memory_gb)

    @property
    def total_vcpus(self):
        return self.vcpus + self.shared_vcpus

    @property
    def total_vm_memory_gb(self):
        return self.vm_memory_gb + self.shared_memory_gb


@dataclass
class Capacity:
    hosts: list = field(default_factory=list)
    vm_count: int = 0
    vcpus: float = 0
    vm_memory_gb: float = 0
    unplaced_vm_count: int = 0
    # True for one host of a cluster: vcpus/vm_memory_gb include its share of the unplaced VMs.
    host_share: bool = False
    # Some VM is pinned to a host, so VMs without a host are not spread automatically.
    manual_placement: bool = False
    # VMs without a host were spread over the hosts.
    distributed: bool = False

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


def _weights(hosts, attribute):
    """Share per host proportional to its size; equal shares if no host has the value recorded."""
    sizes = [getattr(host, attribute) or 0 for host in hosts]
    total = sum(sizes)
    if not total:
        return [1 / len(hosts)] * len(hosts)
    return [size / total for size in sizes]


def build_capacity(hosts, vms):
    """Aggregate hosts and VMs.

    hosts: iterable of Host (memory in GB).
    vms:   iterable of (host key or None, vcpus, memory in MB, status).

    VMs without a fixed host (only a cluster) are spread over the hosts in proportion to
    their size: vCPUs by threads, memory by RAM. As soon as any VM of the cluster (in any
    status) is pinned to one of its hosts, the placement is managed by hand and nothing is
    spread; the unplaced VMs then only count towards the cluster totals.
    """
    capacity = Capacity(hosts=list(hosts))
    by_key = {host.key: host for host in capacity.hosts}
    unplaced_vcpus = unplaced_memory_gb = 0
    for host_key, vcpus, memory_mb, status in vms:
        if host_key in by_key:
            capacity.manual_placement = True
        if status in INACTIVE_VM_STATUSES:
            continue
        vcpus = float(vcpus or 0)
        memory_gb = (memory_mb or 0) / 1024
        capacity.vm_count += 1
        capacity.vcpus += vcpus
        capacity.vm_memory_gb += memory_gb
        host = by_key.get(host_key)
        if host is None:
            capacity.unplaced_vm_count += 1
            unplaced_vcpus += vcpus
            unplaced_memory_gb += memory_gb
        else:
            host.vm_count += 1
            host.vcpus += vcpus
            host.vm_memory_gb += memory_gb

    if capacity.hosts and capacity.unplaced_vm_count and not capacity.manual_placement:
        capacity.distributed = True
        for host, weight in zip(capacity.hosts, _weights(capacity.hosts, "threads"), strict=True):
            host.shared_vcpus = unplaced_vcpus * weight
        for host, weight in zip(capacity.hosts, _weights(capacity.hosts, "memory_gb"), strict=True):
            host.shared_memory_gb = unplaced_memory_gb * weight
    return capacity


def host_capacity(cluster_capacity, host):
    """A Capacity for one host of a cluster, including its share of the VMs without a fixed host."""
    return Capacity(
        hosts=[host],
        vm_count=host.vm_count,
        vcpus=host.total_vcpus,
        vm_memory_gb=host.total_vm_memory_gb,
        unplaced_vm_count=cluster_capacity.unplaced_vm_count,
        host_share=True,
        manual_placement=cluster_capacity.manual_placement,
        distributed=cluster_capacity.distributed,
    )
