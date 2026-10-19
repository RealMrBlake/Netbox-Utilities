from netbox.api.viewsets import NetBoxModelViewSet

from .. import disk_filtersets
from ..models import Disk, DiskBayLayout, DiskBayTemplate, RAIDGroup
from . import serializers


class DiskViewSet(NetBoxModelViewSet):
    queryset = Disk.objects.select_related("device", "raid_group", "tenant")
    serializer_class = serializers.DiskSerializer
    filterset_class = disk_filtersets.DiskFilterSet


class RAIDGroupViewSet(NetBoxModelViewSet):
    queryset = RAIDGroup.objects.select_related("device").prefetch_related("disks")
    serializer_class = serializers.RAIDGroupSerializer
    filterset_class = disk_filtersets.RAIDGroupFilterSet


class DiskBayLayoutViewSet(NetBoxModelViewSet):
    queryset = DiskBayLayout.objects.select_related("device")
    serializer_class = serializers.DiskBayLayoutSerializer
    filterset_class = disk_filtersets.DiskBayLayoutFilterSet


class DiskBayTemplateViewSet(NetBoxModelViewSet):
    queryset = DiskBayTemplate.objects.select_related("device_type")
    serializer_class = serializers.DiskBayTemplateSerializer
    filterset_class = disk_filtersets.DiskBayTemplateFilterSet
