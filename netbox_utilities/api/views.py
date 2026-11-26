from netbox.api.authentication import TokenPermissions
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.viewsets import ModelViewSet

from .. import disk_filtersets, hardware_filtersets
from ..models import CableVLANAssignment, CPUModel, DeviceHardware, Disk, DiskBayLayout, DiskBayTemplate, RAIDGroup, SwitchStack
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


class CPUModelViewSet(NetBoxModelViewSet):
    queryset = CPUModel.objects.all()
    serializer_class = serializers.CPUModelSerializer
    filterset_class = hardware_filtersets.CPUModelFilterSet


class DeviceHardwareViewSet(NetBoxModelViewSet):
    queryset = DeviceHardware.objects.select_related("device", "cpu")
    serializer_class = serializers.DeviceHardwareSerializer
    filterset_class = hardware_filtersets.DeviceHardwareFilterSet


class SwitchStackViewSet(ModelViewSet):
    """Plain model without change log or tags; filter with ``?device_id=`` or ``?member_id=``."""

    queryset = SwitchStack.objects.prefetch_related("members").order_by("pk")
    serializer_class = serializers.SwitchStackSerializer
    permission_classes = [TokenPermissions]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("device_id"):
            queryset = queryset.filter(device_id__in=params.getlist("device_id"))
        if params.get("member_id"):
            queryset = queryset.filter(members__in=params.getlist("member_id")).distinct()
        return queryset


class CableVLANAssignmentViewSet(ModelViewSet):
    """VLANs of cable connections; filter with ``?cable_id=``."""

    queryset = CableVLANAssignment.objects.prefetch_related("vlans").order_by("pk")
    serializer_class = serializers.CableVLANAssignmentSerializer
    permission_classes = [TokenPermissions]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("cable_id"):
            queryset = queryset.filter(cable_id__in=self.request.query_params.getlist("cable_id"))
        return queryset
