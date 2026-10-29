from dcim.models import Device
from django.db.models import Count
from django.urls import reverse
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from . import hardware, hardware_filtersets, hardware_forms, hardware_tables
from .models import CPUModel, DeviceHardware
from .runtime import hardware_enabled


def host_entry(device):
    """hardware.Host for a device, with or without recorded CPU/RAM."""
    record = getattr(device, "netbox_utilities_hardware", None)
    if record is None:
        return hardware.Host(name=device.name, key=device.pk)
    return hardware.Host(
        name=device.name,
        key=device.pk,
        cores=record.total_cores,
        threads=record.total_threads,
        memory_gb=record.memory_gb,
    )


def vm_rows(vms):
    return [(vm.device_id, vm.vcpus, vm.memory, vm.status) for vm in vms]


def capacity_context(capacity):
    return {
        "capacity": capacity,
        "vcpu_per_core": hardware.format_ratio(capacity.vcpu_per_core),
        "vcpu_per_thread": hardware.format_ratio(capacity.vcpu_per_thread),
        "memory": hardware.format_memory(capacity.memory_gb),
        "vm_memory": hardware.format_memory(round(capacity.vm_memory_gb, 1)),
        "failover_memory": hardware.format_memory(capacity.failover_memory_gb),
        "capacity_warnings": capacity.warnings(hardware.vcpu_ratio_warning()),
    }


def hardware_tab_url(device):
    return reverse("dcim:device_hardware", kwargs={"pk": device.pk})


def hardware_tab_badge(device):
    """Total cores of the device; "—" without CPU; None hides the tab for other devices."""
    if not hardware_enabled():
        return None
    record = DeviceHardware.objects.filter(device=device).select_related("cpu").first()
    if record is None:
        return "—" if hardware.supports_hardware(device) else None
    return str(record.total_cores) if record.cpu_id else "—"


@register_model_view(Device, "hardware", path="hardware")
class DeviceHardwareTabView(generic.ObjectView):
    queryset = Device.objects.all()
    template_name = "netbox_utilities/device_hardware.html"
    tab = ViewTab(
        label="CPU & RAM",
        badge=hardware_tab_badge,
        permission="netbox_utilities.view_devicehardware",
        weight=2060,
        hide_if_empty=True,
    )

    def get_extra_context(self, request, instance):
        return device_hardware_context(request, instance)


def device_hardware_context(request, device):
    """The "CPU & RAM" tab: CPU/RAM and, for virtualization hosts, the VMs running on it."""
    record = DeviceHardware.objects.filter(device=device).select_related("cpu").first()
    context = {
        "record": record,
        "supported": hardware.supports_hardware(device),
        "can_add": request.user.has_perm("netbox_utilities.add_devicehardware"),
        "can_change": request.user.has_perm("netbox_utilities.change_devicehardware"),
        "add_url": f"{reverse('plugins:netbox_utilities:devicehardware_add')}?device={device.pk}"
        f"&return_url={hardware_tab_url(device)}",
    }
    vms = list(
        VirtualMachine.objects.restrict(request.user, "view")
        .filter(device=device)
        .select_related("tenant")
        .order_by("name")
    )
    if device.cluster_id:
        # Includes this host's share of the cluster VMs that have no fixed host.
        cluster_capacity, _ = build_cluster_capacity(request, device.cluster_id, extra_host=device)
        host = next(host for host in cluster_capacity.hosts if host.key == device.pk)
        capacity = hardware.host_capacity(cluster_capacity, host)
    elif vms:
        capacity = hardware.build_capacity([host_entry(device)], vm_rows(vms))
        host = capacity.hosts[0]
    if device.cluster_id or vms:
        context.update(capacity_context(capacity))
        context["host"] = host
        context["vms"] = vms
        context["vm_list_url"] = f"{reverse('virtualization:virtualmachine_list')}?device_id={device.pk}"
    return context


def build_cluster_capacity(request, cluster_id, extra_host=None):
    """Capacity of a cluster's hosts and VMs; returns (capacity, host devices in the same order)."""
    hosts = list(
        Device.objects.restrict(request.user, "view")
        .filter(cluster_id=cluster_id)
        .select_related("netbox_utilities_hardware__cpu")
        .order_by("name")
    )
    if extra_host is not None and all(host.pk != extra_host.pk for host in hosts):
        hosts.append(extra_host)
    vms = VirtualMachine.objects.restrict(request.user, "view").filter(cluster_id=cluster_id)
    return hardware.build_capacity([host_entry(device) for device in hosts], vm_rows(vms)), hosts


def cluster_capacity_context(request, cluster):
    capacity, hosts = build_cluster_capacity(request, cluster.pk)
    rows = []
    for device, host in zip(hosts, capacity.hosts, strict=True):
        record = getattr(device, "netbox_utilities_hardware", None)
        rows.append(
            {
                "device": device,
                "record": record,
                "host": host,
                "memory": hardware.format_memory(host.memory_gb),
                "vm_memory": hardware.format_memory(round(host.total_vm_memory_gb, 1)),
                "memory_percent": hardware.percent(host.total_vm_memory_gb, host.memory_gb),
                "vcpu_per_core": hardware.format_ratio(host.total_vcpus / host.cores if host.cores else None),
            }
        )
    return {
        **capacity_context(capacity),
        "rows": rows,
        "hardware_list_url": f"{reverse('plugins:netbox_utilities:devicehardware_list')}?cluster_id={cluster.pk}",
        "can_add": request.user.has_perm("netbox_utilities.add_devicehardware"),
    }


def vm_host_context(request, vm):
    """Panel on the VM page: the host's CPU and what share of it the VM gets."""
    device = vm.device
    if device is None and vm.cluster_id:
        hosts = Device.objects.filter(cluster_id=vm.cluster_id)
        records = list(DeviceHardware.objects.filter(device__in=hosts).select_related("cpu", "device"))
    else:
        records = list(DeviceHardware.objects.filter(device=device).select_related("cpu", "device")) if device else []
    cpus = sorted({str(record.cpu) for record in records if record.cpu_id})
    smallest = min((record.total_threads for record in records if record.total_threads), default=None)
    return {
        "device": device,
        "records": records,
        "cpus": cpus,
        "vcpus": vm.vcpus,
        "smallest_threads": smallest,
        "vcpu_share": hardware.percent(vm.vcpus or 0, smallest),
        "oversized": bool(smallest and vm.vcpus and vm.vcpus > smallest),
    }


#
# CPU models
#


@register_model_view(CPUModel, "list", path="", detail=False)
class CPUModelListView(generic.ObjectListView):
    queryset = CPUModel.objects.annotate(device_count=Count("devices"))
    table = hardware_tables.CPUModelTable
    filterset = hardware_filtersets.CPUModelFilterSet
    filterset_form = hardware_forms.CPUModelFilterForm


@register_model_view(CPUModel)
class CPUModelView(generic.ObjectView):
    queryset = CPUModel.objects.all()

    def get_extra_context(self, request, instance):
        records = DeviceHardware.objects.restrict(request.user, "view").filter(cpu=instance)
        return {
            "devices_table": hardware_tables.DeviceHardwareTable(
                records.select_related("device", "device__cluster", "cpu"), orderable=False
            ),
            "device_count": records.count(),
        }


@register_model_view(CPUModel, "add", detail=False)
@register_model_view(CPUModel, "edit")
class CPUModelEditView(generic.ObjectEditView):
    queryset = CPUModel.objects.all()
    form = hardware_forms.CPUModelForm


@register_model_view(CPUModel, "delete")
class CPUModelDeleteView(generic.ObjectDeleteView):
    queryset = CPUModel.objects.all()


@register_model_view(CPUModel, "bulk_import", path="import", detail=False)
class CPUModelBulkImportView(generic.BulkImportView):
    queryset = CPUModel.objects.all()
    model_form = hardware_forms.CPUModelImportForm


@register_model_view(CPUModel, "bulk_delete", path="delete", detail=False)
class CPUModelBulkDeleteView(generic.BulkDeleteView):
    queryset = CPUModel.objects.annotate(device_count=Count("devices"))
    filterset = hardware_filtersets.CPUModelFilterSet
    table = hardware_tables.CPUModelTable


#
# CPU & RAM per device
#


@register_model_view(DeviceHardware, "list", path="", detail=False)
class DeviceHardwareListView(generic.ObjectListView):
    queryset = DeviceHardware.objects.select_related("device", "device__cluster", "cpu")
    table = hardware_tables.DeviceHardwareTable
    filterset = hardware_filtersets.DeviceHardwareFilterSet
    filterset_form = hardware_forms.DeviceHardwareFilterForm


@register_model_view(DeviceHardware)
class DeviceHardwareView(generic.ObjectView):
    queryset = DeviceHardware.objects.select_related("device", "cpu")

    def get_extra_context(self, request, instance):
        return device_hardware_context(request, instance.device)


@register_model_view(DeviceHardware, "add", detail=False)
@register_model_view(DeviceHardware, "edit")
class DeviceHardwareEditView(generic.ObjectEditView):
    queryset = DeviceHardware.objects.all()
    form = hardware_forms.DeviceHardwareForm

    def get_return_url(self, request, obj=None):
        if obj is not None and obj.pk and obj.device_id and "return_url" not in request.GET:
            return hardware_tab_url(obj.device)
        return super().get_return_url(request, obj)


@register_model_view(DeviceHardware, "delete")
class DeviceHardwareDeleteView(generic.ObjectDeleteView):
    queryset = DeviceHardware.objects.all()


@register_model_view(DeviceHardware, "bulk_import", path="import", detail=False)
class DeviceHardwareBulkImportView(generic.BulkImportView):
    queryset = DeviceHardware.objects.all()
    model_form = hardware_forms.DeviceHardwareImportForm


@register_model_view(DeviceHardware, "bulk_delete", path="delete", detail=False)
class DeviceHardwareBulkDeleteView(generic.BulkDeleteView):
    queryset = DeviceHardware.objects.select_related("device", "cpu")
    filterset = hardware_filtersets.DeviceHardwareFilterSet
    table = hardware_tables.DeviceHardwareTable
