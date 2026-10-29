import django_filters
from dcim.models import Device
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant
from virtualization.models import Cluster

from .models import CPUManufacturerChoices, CPUModel, DeviceHardware, MemoryTypeChoices


class CPUModelFilterSet(NetBoxModelFilterSet):
    manufacturer = django_filters.MultipleChoiceFilter(choices=CPUManufacturerChoices)
    family = django_filters.CharFilter(lookup_expr="icontains")
    socket = django_filters.CharFilter(lookup_expr="iexact")
    cores = django_filters.NumberFilter()
    cores__gte = django_filters.NumberFilter(field_name="cores", lookup_expr="gte", label="Kerne ab")
    cores__lte = django_filters.NumberFilter(field_name="cores", lookup_expr="lte", label="Kerne bis")
    launch_year = django_filters.NumberFilter()
    launch_year__gte = django_filters.NumberFilter(field_name="launch_year", lookup_expr="gte", label="Ab Jahr")
    in_use = django_filters.BooleanFilter(method="filter_in_use", label="In Verwendung")

    class Meta:
        model = CPUModel
        fields = ("id", "name", "max_sockets", "builtin")

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        query = Q()
        # "Gold 6338", "epyc 7543" or "intel 6338": every word must match somewhere.
        for word in value.split():
            query &= (
                Q(name__icontains=word)
                | Q(family__icontains=word)
                | Q(manufacturer__iexact=word)
                | Q(socket__iexact=word)
            )
        return queryset.filter(query)

    def filter_in_use(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(devices__isnull=not value).distinct()


class DeviceHardwareFilterSet(NetBoxModelFilterSet):
    device_id = django_filters.ModelMultipleChoiceFilter(queryset=Device.objects.all(), label="Gerät (ID)")
    device = django_filters.ModelMultipleChoiceFilter(
        field_name="device__name", queryset=Device.objects.all(), to_field_name="name", label="Gerät (Name)"
    )
    cpu_id = django_filters.ModelMultipleChoiceFilter(queryset=CPUModel.objects.all(), label="CPU-Modell (ID)")
    cluster_id = django_filters.ModelMultipleChoiceFilter(
        field_name="device__cluster", queryset=Cluster.objects.all(), label="Cluster (ID)"
    )
    manufacturer = django_filters.MultipleChoiceFilter(field_name="cpu__manufacturer", choices=CPUManufacturerChoices)
    memory_type = django_filters.MultipleChoiceFilter(choices=MemoryTypeChoices)
    memory_gb__gte = django_filters.NumberFilter(field_name="memory_gb", lookup_expr="gte", label="RAM ab (GB)")
    # Read by the global tenant filter middleware, which may pass several tenants of a group.
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        field_name="device__tenant", queryset=Tenant.objects.all(), label="Mandant (ID)"
    )

    class Meta:
        model = DeviceHardware
        fields = ("id", "cpu_count", "memory_gb")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(device__name__icontains=value)
            | Q(cpu__name__icontains=value)
            | Q(cpu__family__icontains=value)
            | Q(description__icontains=value)
        )
