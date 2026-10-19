from datetime import timedelta

import django_filters
from dcim.models import Device, DeviceType
from django.db.models import Q
from django.utils import timezone
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant

from . import disks
from .models import (
    Disk,
    DiskBayLayout,
    DiskBayTemplate,
    DiskFormFactorChoices,
    DiskInterfaceChoices,
    DiskStatusChoices,
    DiskTypeChoices,
    RAIDGroup,
    RAIDLevelChoices,
)


def warnings_query(today=None):
    """Disks which show at least one warning in the UI (see disks.disk_warnings)."""
    today = today or timezone.localdate()
    settings = disks.warning_settings()
    age_limit = disks.add_years(today, -settings["age_years"])
    return ~Q(status=disks.STATUS_REPLACED) & (
        Q(status=disks.STATUS_FAILED)
        | Q(warranty_end__lte=today + timedelta(days=settings["warranty_days"]))
        | Q(manufacture_date__lte=age_limit)
        | Q(manufacture_date__isnull=True, install_date__lte=age_limit)
    )


class DiskFilterSet(NetBoxModelFilterSet):
    device_id = django_filters.ModelMultipleChoiceFilter(queryset=Device.objects.all(), label="Gerät (ID)")
    device = django_filters.ModelMultipleChoiceFilter(
        field_name="device__name", queryset=Device.objects.all(), to_field_name="name", label="Gerät (Name)"
    )
    tenant_id = django_filters.ModelMultipleChoiceFilter(queryset=Tenant.objects.all(), label="Mandant (ID)")
    raid_group_id = django_filters.ModelMultipleChoiceFilter(queryset=RAIDGroup.objects.all(), label="RAID-Gruppe (ID)")
    bay_id = django_filters.ModelMultipleChoiceFilter(queryset=DiskBayLayout.objects.all(), label="Bereich (ID)")
    bay = django_filters.CharFilter(field_name="bay__name", lookup_expr="iexact", label="Bereich (Name)")
    status = django_filters.MultipleChoiceFilter(choices=DiskStatusChoices)
    disk_type = django_filters.MultipleChoiceFilter(choices=DiskTypeChoices)
    interface = django_filters.MultipleChoiceFilter(choices=DiskInterfaceChoices)
    form_factor = django_filters.MultipleChoiceFilter(choices=DiskFormFactorChoices)
    manufacturer = django_filters.CharFilter(lookup_expr="icontains")
    serial = django_filters.CharFilter(lookup_expr="iexact")
    occupied = django_filters.BooleanFilter(method="filter_occupied", label="Belegt einen Steckplatz")
    warranty = django_filters.ChoiceFilter(
        method="filter_warranty",
        choices=(("expired", "Abgelaufen"), ("expiring", "Läuft bald ab"), ("valid", "Gültig")),
        label="Garantie",
    )
    older_than_years = django_filters.NumberFilter(method="filter_older_than", label="Älter als (Jahre)")
    has_warnings = django_filters.BooleanFilter(method="filter_has_warnings", label="Mit Warnungen")

    class Meta:
        model = Disk
        fields = ("id", "slot", "model", "firmware", "capacity_gb", "install_date", "warranty_end")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(serial__icontains=value)
            | Q(model__icontains=value)
            | Q(manufacturer__icontains=value)
            | Q(device__name__icontains=value)
            | Q(description__icontains=value)
        )

    def filter_occupied(self, queryset, name, value):
        query = Q(status__in=disks.SLOT_OCCUPYING_STATUSES)
        return queryset.filter(query) if value else queryset.exclude(query)

    def filter_warranty(self, queryset, name, value):
        today = timezone.localdate()
        soon = today + timedelta(days=disks.warning_settings()["warranty_days"])
        if value == "expired":
            return queryset.filter(warranty_end__lt=today)
        if value == "expiring":
            return queryset.filter(warranty_end__gte=today, warranty_end__lte=soon)
        if value == "valid":
            return queryset.filter(warranty_end__gt=soon)
        return queryset

    def filter_older_than(self, queryset, name, value):
        if not value:
            return queryset
        limit = disks.add_years(timezone.localdate(), -int(value))
        return queryset.filter(
            Q(manufacture_date__lte=limit) | Q(manufacture_date__isnull=True, install_date__lte=limit)
        )

    def filter_has_warnings(self, queryset, name, value):
        query = warnings_query()
        return queryset.filter(query) if value else queryset.exclude(query)


class RAIDGroupFilterSet(NetBoxModelFilterSet):
    device_id = django_filters.ModelMultipleChoiceFilter(queryset=Device.objects.all(), label="Gerät (ID)")
    level = django_filters.MultipleChoiceFilter(choices=RAIDLevelChoices)

    class Meta:
        model = RAIDGroup
        fields = ("id", "name", "spans")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(device__name__icontains=value) | Q(description__icontains=value)
        )


class DiskBayLayoutFilterSet(NetBoxModelFilterSet):
    device_id = django_filters.ModelMultipleChoiceFilter(queryset=Device.objects.all(), label="Gerät (ID)")

    class Meta:
        model = DiskBayLayout
        fields = ("id", "name", "weight", "slot_count", "rows", "first_slot", "numbering", "form_factor")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(device__name__icontains=value) | Q(name__icontains=value))


class DiskBayTemplateFilterSet(NetBoxModelFilterSet):
    device_type_id = django_filters.ModelMultipleChoiceFilter(queryset=DeviceType.objects.all(), label="Gerätetyp (ID)")

    class Meta:
        model = DiskBayTemplate
        fields = ("id", "name", "weight", "slot_count", "rows", "first_slot", "numbering", "form_factor")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(device_type__model__icontains=value) | Q(name__icontains=value))
