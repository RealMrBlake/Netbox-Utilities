from dcim.models import Device
from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm, NetBoxModelImportForm
from utilities.forms.fields import (
    CommentField,
    CSVChoiceField,
    CSVModelChoiceField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
    TagFilterField,
)
from utilities.forms.rendering import FieldSet
from virtualization.models import Cluster

from .models import CPUManufacturerChoices, CPUModel, DeviceHardware, MemoryTypeChoices


class CPUModelForm(NetBoxModelForm):
    fieldsets = (
        FieldSet("manufacturer", "family", "name", "socket", "launch_year", name="CPU"),
        FieldSet("cores", "threads", "base_clock_ghz", "boost_clock_ghz", "tdp_watts", "max_sockets", name="Leistung"),
        FieldSet("description", "tags", name="Sonstiges"),
    )

    class Meta:
        model = CPUModel
        fields = (
            "manufacturer",
            "family",
            "name",
            "socket",
            "launch_year",
            "cores",
            "threads",
            "base_clock_ghz",
            "boost_clock_ghz",
            "tdp_watts",
            "max_sockets",
            "description",
            "tags",
        )

    def save(self, *args, **kwargs):
        # Edited catalogue entries keep their values when the catalogue is refreshed.
        if self.instance.pk and self.instance.builtin and self.has_changed():
            self.instance.customized = True
        return super().save(*args, **kwargs)


class CPUModelImportForm(NetBoxModelImportForm):
    manufacturer = CSVChoiceField(label="Hersteller", choices=CPUManufacturerChoices)

    class Meta:
        model = CPUModel
        fields = (
            "manufacturer",
            "family",
            "name",
            "socket",
            "launch_year",
            "cores",
            "threads",
            "base_clock_ghz",
            "boost_clock_ghz",
            "tdp_watts",
            "max_sockets",
            "description",
            "tags",
        )


class CPUModelFilterForm(NetBoxModelFilterSetForm):
    model = CPUModel
    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("manufacturer", "family", "socket", "cores__gte", "launch_year__gte", "in_use", name="CPU"),
    )
    manufacturer = forms.MultipleChoiceField(label="Hersteller", choices=CPUManufacturerChoices, required=False)
    family = forms.CharField(label="Familie", required=False)
    socket = forms.CharField(label="Sockel", required=False)
    cores__gte = forms.IntegerField(label="Kerne ab", required=False)
    launch_year__gte = forms.IntegerField(label="Ab Jahr", required=False)
    in_use = forms.NullBooleanField(
        label="In Verwendung",
        required=False,
        widget=forms.Select(choices=(("", "—"), ("true", "Ja"), ("false", "Nein"))),
    )
    tag = TagFilterField(model)


class DeviceHardwareForm(NetBoxModelForm):
    device = DynamicModelChoiceField(label="Gerät", queryset=Device.objects.all(), selector=True)
    cpu = DynamicModelChoiceField(
        label="CPU-Modell",
        queryset=CPUModel.objects.all(),
        required=False,
        help_text="Suche nach Modell oder Familie, z. B. „6338“, „Gold 6338“ oder „EPYC 7543“.",
    )
    comments = CommentField()

    fieldsets = (
        FieldSet("device", name="Gerät"),
        FieldSet("cpu", "cpu_count", name="CPU"),
        FieldSet(
            "memory_modules", "memory_module_gb", "memory_gb", "memory_type", "memory_speed_mts", name="Arbeitsspeicher"
        ),
        FieldSet("description", "tags", name="Sonstiges"),
    )

    class Meta:
        model = DeviceHardware
        fields = (
            "device",
            "cpu",
            "cpu_count",
            "memory_modules",
            "memory_module_gb",
            "memory_gb",
            "memory_type",
            "memory_speed_mts",
            "description",
            "comments",
            "tags",
        )
        help_texts = {
            "memory_gb": "Leer lassen, um ihn aus Anzahl × Größe der Module zu berechnen.",
        }


class DeviceHardwareImportForm(NetBoxModelImportForm):
    device = CSVModelChoiceField(
        label="Gerät", queryset=Device.objects.all(), to_field_name="name", help_text="Name des Geräts"
    )
    cpu = CSVModelChoiceField(
        label="CPU-Modell",
        queryset=CPUModel.objects.all(),
        to_field_name="name",
        required=False,
        help_text="Modellname aus dem Katalog, z. B. Xeon Gold 6338",
    )
    memory_type = CSVChoiceField(label="RAM-Typ", choices=MemoryTypeChoices, required=False)

    class Meta:
        model = DeviceHardware
        fields = (
            "device",
            "cpu",
            "cpu_count",
            "memory_gb",
            "memory_type",
            "memory_modules",
            "memory_module_gb",
            "memory_speed_mts",
            "description",
            "comments",
            "tags",
        )


class DeviceHardwareFilterForm(NetBoxModelFilterSetForm):
    model = DeviceHardware
    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("device_id", "cluster_id", "cpu_id", "manufacturer", "memory_type", "memory_gb__gte", name="Hardware"),
    )
    device_id = DynamicModelMultipleChoiceField(queryset=Device.objects.all(), required=False, label="Gerät")
    cluster_id = DynamicModelMultipleChoiceField(queryset=Cluster.objects.all(), required=False, label="Cluster")
    cpu_id = DynamicModelMultipleChoiceField(queryset=CPUModel.objects.all(), required=False, label="CPU-Modell")
    manufacturer = forms.MultipleChoiceField(label="Hersteller", choices=CPUManufacturerChoices, required=False)
    memory_type = forms.MultipleChoiceField(label="RAM-Typ", choices=MemoryTypeChoices, required=False)
    memory_gb__gte = forms.IntegerField(label="RAM ab (GB)", required=False)
    tag = TagFilterField(model)
