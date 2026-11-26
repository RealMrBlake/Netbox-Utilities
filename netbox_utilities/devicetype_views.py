from dcim.filtersets import DeviceTypeFilterSet
from dcim.models import DeviceType
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from . import devicetype_export

PREFETCH = [
    "consoleporttemplates",
    "consoleserverporttemplates",
    "powerporttemplates",
    "poweroutlettemplates__power_port",
    "interfacetemplates",
    "rearporttemplates",
    "frontporttemplates",
    "modulebaytemplates",
    "devicebaytemplates",
    "inventoryitemtemplates__manufacturer",
]


def _queryset(request):
    if not request.user.has_perm("dcim.view_devicetype"):
        raise PermissionDenied
    return DeviceType.objects.restrict(request.user, "view").select_related("manufacturer").prefetch_related(*PREFETCH)


class DeviceTypeYAMLExportView(LoginRequiredMixin, View):
    def get(self, request, pk):
        device_type = get_object_or_404(_queryset(request), pk=pk)
        response = HttpResponse(devicetype_export.device_type_to_yaml(device_type), content_type="application/yaml; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{devicetype_export.filename(device_type)}"'
        return response


class DeviceTypeBulkYAMLExportView(LoginRequiredMixin, View):
    """Exports the current (filtered) device type list, or ?id=... selections, as a ZIP."""

    def get(self, request):
        device_types = DeviceTypeFilterSet(request.GET, queryset=_queryset(request)).qs.order_by("manufacturer__name", "model")
        response = HttpResponse(devicetype_export.device_types_to_zip(device_types), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="device-types.zip"'
        return response
