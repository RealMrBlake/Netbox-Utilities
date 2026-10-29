from dcim.api.serializers import DeviceSerializer, DeviceTypeSerializer
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from tenancy.api.serializers import TenantSerializer

from ..models import CPUModel, DeviceHardware, Disk, DiskBayLayout, DiskBayTemplate, RAIDGroup

LAYOUT_FIELDS = ("name", "weight", "slot_count", "rows", "first_slot", "numbering", "form_factor")


class RAIDGroupSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_utilities-api:raidgroup-detail")
    device = DeviceSerializer(nested=True)
    usable_capacity_gb = serializers.IntegerField(read_only=True, allow_null=True)
    is_degraded = serializers.BooleanField(read_only=True)

    class Meta:
        model = RAIDGroup
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "device",
            "name",
            "level",
            "spans",
            "description",
            "usable_capacity_gb",
            "is_degraded",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "level")


class DiskSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_utilities-api:disk-detail")
    device = DeviceSerializer(nested=True)
    bay = serializers.PrimaryKeyRelatedField(
        queryset=DiskBayLayout.objects.all(), required=False, allow_null=True, help_text="ID des Bereichs"
    )
    raid_group = RAIDGroupSerializer(nested=True, required=False, allow_null=True)
    tenant = TenantSerializer(nested=True, read_only=True)
    warnings = serializers.SerializerMethodField()

    class Meta:
        model = Disk
        fields = (
            "id",
            "url",
            "display_url",
            "display",
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
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "device", "slot", "serial", "capacity_gb", "status")

    def get_warnings(self, obj) -> list[str]:
        return [text for _, text in obj.warnings]


class DiskBayLayoutSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_utilities-api:diskbaylayout-detail")
    device = DeviceSerializer(nested=True)

    class Meta:
        model = DiskBayLayout
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "device",
            *LAYOUT_FIELDS,
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "device", "name", "slot_count")


class DiskBayTemplateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_utilities-api:diskbaytemplate-detail")
    device_type = DeviceTypeSerializer(nested=True)

    class Meta:
        model = DiskBayTemplate
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "device_type",
            *LAYOUT_FIELDS,
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "device_type", "name", "slot_count")


class CPUModelSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_utilities-api:cpumodel-detail")
    display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CPUModel
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "manufacturer",
            "family",
            "name",
            "cores",
            "threads",
            "base_clock_ghz",
            "boost_clock_ghz",
            "tdp_watts",
            "socket",
            "launch_year",
            "max_sockets",
            "builtin",
            "customized",
            "description",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "manufacturer", "name", "cores", "threads")

    def get_display(self, obj):
        # Shown in the CPU select: "Intel Xeon Gold 6338 – 32 Kerne / 64 Threads, 2 / 3,2 GHz".
        return f"{obj} – {obj.summary}"


class DeviceHardwareSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_utilities-api:devicehardware-detail")
    device = DeviceSerializer(nested=True)
    cpu = CPUModelSerializer(nested=True, required=False, allow_null=True)
    total_cores = serializers.IntegerField(read_only=True, allow_null=True)
    total_threads = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = DeviceHardware
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "device",
            "cpu",
            "cpu_count",
            "total_cores",
            "total_threads",
            "memory_gb",
            "memory_type",
            "memory_modules",
            "memory_module_gb",
            "memory_speed_mts",
            "description",
            "comments",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "device", "cpu", "cpu_count", "memory_gb")
