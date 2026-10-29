from dcim.models import Device
from django.db.models import Count
from django.urls import reverse
from netbox.views import generic
from utilities.views import register_model_view
from virtualization.models import VirtualMachine

from . import hardware, hardware_filtersets, hardware_forms, hardware_tables
from .models import CPUModel, DeviceHardware


def host_entry(device):
    """hardware.Host for a device, with or without recorded CPU/RAM."""
    record = getattr(device, "netbox_utilities_hardware", None)
    if record is None:
        return hardware.Host(name=device.name)
    return hardware.Host(
        name=device.name,
        cores=record.total_cores,
        threads=record.total_threads,
        memory_gb=record.memory_gb,
    )


def vm_rows(vms):
    return [(vm.device.name if vm.device_id else None, vm.vcpus, vm.memory, vm.status) for vm in vms]


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


def device_hardware_context(request, device):
    """Panel on the device page: CPU/RAM and, for virtualization hosts, the VMs running on it."""
    record = DeviceHardware.objects.filter(device=device).select_related("cpu").first()
    context = {
        "record": record,
        "can_add": request.user.has_perm("netbox_utilities.add_devicehardware"),
        "can_change": request.user.has_perm("netbox_utilities.change_devicehardware"),
        "add_url": f"{reverse('plugins:netbox_utilities:devicehardware_add')}?device={device.pk}"
        f"&return_url={device.get_absolute_url()}",
    }
    vms = list(VirtualMachine.objects.restrict(request.user, "view").filter(device=device))
    if vms or device.cluster_id:
        capacity = hardware.build_capacity([host_entry(device)], vm_rows(vms))
        context.update(capacity_context(capacity))
        context["host"] = capacity.hosts[0]
        context["vm_list_url"] = f"{reverse('virtualization:virtualmachine_list')}?device_id={device.pk}"
    return context


def cluster_capacity_context(request, cluster):
    hosts = list(
        Device.objects.restrict(request.user, "view")
        .filter(cluster=cluster)
        .select_related("netbox_utilities_hardware__cpu")
        .order_by("name")
    )
    vms = VirtualMachine.objects.restrict(request.user, "view").filter(cluster=cluster).select_related("device")
    capacity = hardware.build_capacity([host_entry(device) for device in hosts], vm_rows(vms))
    rows = []
    for device, host in zip(hosts, capacity.hosts, strict=True):
        record = getattr(device, "netbox_utilities_hardware", None)
        rows.append(
            {
                "device": device,
                "record": record,
                "host": host,
                "memory": hardware.format_memory(host.memory_gb),
                "vm_memory": hardware.format_memory(round(host.vm_memory_gb, 1)),
                "memory_percent": hardware.percent(host.vm_memory_gb, host.memory_gb),
                "vcpu_per_core": hardware.format_ratio(host.vcpus / host.cores if host.cores else None),
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
            return obj.device.get_absolute_url()
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
