from itertools import groupby
from urllib.parse import urlencode

from dcim.models import Device
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from netbox.plugins import get_plugin_config
from netbox.views import generic
from utilities.views import ContentTypePermissionRequiredMixin, ViewTab, register_model_view

from . import disk_filtersets, disk_forms, disk_tables, disks
from .models import Disk, DiskBayLayout, DiskBayTemplate, RAIDGroup

LAYOUT_FIELDS = disk_forms.LAYOUT_FIELDS


def disk_tab_badge(device):
    """Number of installed disks; None hides the tab for roles without disks.

    The count is returned as a string so that "0" still shows the tab (hide_if_empty).
    """
    if not get_plugin_config("netbox_utilities", "disks_enabled") or not disks.supports_disks(device):
        return None
    return str(Disk.objects.filter(device=device, status__in=disks.SLOT_OCCUPYING_STATUSES).count())


def device_disk_context(device):
    layout = DiskBayLayout.objects.filter(device=device).first()
    device_disks = list(
        Disk.objects.filter(device=device).select_related("raid_group").order_by("slot", "-removal_date", "pk")
    )
    installed = [disk for disk in device_disks if disk.occupies_slot]
    history = [disk for disk in device_disks if not disk.occupies_slot]
    raid_groups = list(RAIDGroup.objects.filter(device=device).prefetch_related("disks"))
    context = {
        "supported": disks.supports_disks(device),
        "layout": layout,
        "raid_groups": raid_groups,
        "history_table": disk_tables.DeviceDiskHistoryTable(history, orderable=False),
        "history_count": len(history),
        "disk_warnings": [(disk, disk.warnings) for disk in installed if disk.warnings],
    }
    if layout is None:
        template = DiskBayTemplate.objects.filter(device_type_id=device.device_type_id).first()
        initial = {name: getattr(template, name) for name in LAYOUT_FIELDS} if template else {}
        context.update(
            {
                "device_type_template": template,
                "setup_form": disk_forms.DiskBayLayoutForm(initial=initial),
            }
        )
        return context

    by_slot = {disk.slot: disk for disk in installed}
    grid_slots = set(range(layout.first_slot, layout.last_slot + 1))
    usable = [group.usable_capacity_gb for group in raid_groups if group.usable_capacity_gb]
    summary = disks.disk_summary(installed, layout.slot_count)
    summary.update(
        {
            "raw_capacity": disks.format_capacity(summary["raw_capacity_gb"]),
            "usable_capacity": disks.format_capacity(sum(usable)) if usable else None,
            "degraded_groups": sum(1 for group in raid_groups if group.is_degraded),
        }
    )
    context.update(
        {
            "grid": disks.build_slot_grid(layout.slot_count, layout.rows, layout.first_slot, layout.numbering, by_slot),
            "summary": summary,
            "orphaned_disks": [disk for disk in installed if disk.slot not in grid_slots],
            "warning_count": sum(1 for disk in installed if disk.warnings),
        }
    )
    return context


@register_model_view(Device, "disks", path="disks")
class DeviceDisksView(generic.ObjectView):
    queryset = Device.objects.all()
    template_name = "netbox_utilities/device_disks.html"
    tab = ViewTab(
        label="Datenträger",
        badge=disk_tab_badge,
        permission="netbox_utilities.view_disk",
        weight=2050,
        hide_if_empty=True,
    )

    def get_extra_context(self, request, instance):
        return device_disk_context(instance)


class _DeviceDiskActionView(ContentTypePermissionRequiredMixin, View):
    required_permission = "netbox_utilities.add_disk"

    def get_required_permission(self):
        return self.required_permission

    def get_device(self, request, pk):
        return get_object_or_404(Device.objects.restrict(request.user, "view").select_related("role"), pk=pk)

    @staticmethod
    def tab_url(device):
        return reverse("dcim:device_disks", kwargs={"pk": device.pk})


class DeviceDiskSetupView(_DeviceDiskActionView):
    """Wizard on the first visit and later "Layout ändern"."""

    template_name = "netbox_utilities/device_disk_setup.html"

    def get(self, request, pk):
        device = self.get_device(request, pk)
        layout = DiskBayLayout.objects.filter(device=device).first()
        form = disk_forms.DiskBayLayoutForm(instance=layout, initial={"save_as_template": layout is None})
        return render(request, self.template_name, {"object": device, "form": form, "layout": layout})

    def post(self, request, pk):
        device = self.get_device(request, pk)
        layout = DiskBayLayout.objects.filter(device=device).first()

        if "apply_template" in request.POST and layout is None:
            template = get_object_or_404(DiskBayTemplate, device_type_id=device.device_type_id)
            DiskBayLayout.objects.create(device=device, **{name: getattr(template, name) for name in LAYOUT_FIELDS})
            messages.success(request, f"Das Layout der Vorlage „{template}“ wurde übernommen.")
            return redirect(self.tab_url(device))

        if layout is not None:
            layout.snapshot()
        form = disk_forms.DiskBayLayoutForm(request.POST, instance=layout or DiskBayLayout(device=device))
        if form.is_valid():
            layout = form.save()
            if form.cleaned_data.get("save_as_template"):
                DiskBayTemplate.objects.update_or_create(
                    device_type_id=device.device_type_id,
                    defaults={name: getattr(layout, name) for name in LAYOUT_FIELDS},
                )
            messages.success(request, f"{layout.slot_count} Steckplätze wurden gespeichert.")
            return redirect(self.tab_url(device))
        return render(request, self.template_name, {"object": device, "form": form, "layout": layout})


class DeviceDiskBulkFillView(_DeviceDiskActionView):
    template_name = "netbox_utilities/device_disk_fill.html"

    def free_slots(self, device, layout):
        used = set(
            Disk.objects.filter(device=device, status__in=disks.SLOT_OCCUPYING_STATUSES).values_list("slot", flat=True)
        )
        return [slot for slot in range(layout.first_slot, layout.last_slot + 1) if slot not in used]

    def get_layout(self, device):
        return DiskBayLayout.objects.filter(device=device).first()

    def get(self, request, pk):
        device = self.get_device(request, pk)
        layout = self.get_layout(device)
        if layout is None:
            return redirect(self.tab_url(device))
        free = self.free_slots(device, layout)
        selected = [int(slot) for slot in request.GET.getlist("slots") if slot.isdigit()]
        initial = {
            "slots": [slot for slot in selected if slot in free] or free,
            "form_factor": layout.form_factor,
        }
        form = disk_forms.DiskBulkFillForm(device=device, free_slots=free, initial=initial)
        return self._render(request, device, form, free)

    def post(self, request, pk):
        device = self.get_device(request, pk)
        layout = self.get_layout(device)
        if layout is None:
            return redirect(self.tab_url(device))
        free = self.free_slots(device, layout)
        form = disk_forms.DiskBulkFillForm(request.POST, device=device, free_slots=free)
        if form.is_valid():
            new_disks = form.build_disks()
            try:
                with transaction.atomic():
                    for disk in new_disks:
                        disk.full_clean()
                        disk.save()
            except ValidationError as error:
                for message in error.messages:
                    form.add_error(None, message)
            else:
                messages.success(request, f"{len(new_disks)} Datenträger wurden eingebaut.")
                return redirect(self.tab_url(device))
        return self._render(request, device, form, free)

    def _render(self, request, device, form, free):
        return render(
            request,
            self.template_name,
            {"object": device, "form": form, "free_slots": free, "return_url": self.tab_url(device)},
        )


# Parking slot while two disks swap places; the unique (device, slot) constraint
# would otherwise reject the intermediate state.
SWAP_PARKING_SLOT = 32767


class DeviceDiskMoveView(ContentTypePermissionRequiredMixin, View):
    """Drag and drop on the slot grid: move a disk to a free slot or swap two disks."""

    http_method_names = ["post"]

    def get_required_permission(self):
        return "netbox_utilities.change_disk"

    def post(self, request, pk):
        device = get_object_or_404(Device.objects.restrict(request.user, "view"), pk=pk)
        layout = get_object_or_404(DiskBayLayout, device=device)
        installed = Disk.objects.restrict(request.user, "change").filter(
            device=device, status__in=disks.SLOT_OCCUPYING_STATUSES
        )
        try:
            disk = installed.get(pk=int(request.POST.get("disk", "")))
            target_slot = int(request.POST.get("slot", ""))
        except (ValueError, Disk.DoesNotExist):
            return JsonResponse({"error": "Unbekannter Datenträger oder Steckplatz."}, status=400)
        if not layout.first_slot <= target_slot <= layout.last_slot:
            return JsonResponse({"error": f"Steckplatz {target_slot} existiert nicht."}, status=400)
        if target_slot == disk.slot:
            return JsonResponse({"moved": []})

        source_slot = disk.slot
        with transaction.atomic():
            other = (
                Disk.objects.select_for_update()
                .filter(device=device, slot=target_slot, status__in=disks.SLOT_OCCUPYING_STATUSES)
                .first()
            )
            if other is not None and not installed.filter(pk=other.pk).exists():
                return JsonResponse({"error": "Keine Berechtigung für den Datenträger im Ziel."}, status=403)

            disk.snapshot()
            if other is not None:
                other.snapshot()
                disk.slot = SWAP_PARKING_SLOT
                disk.save()
                other.slot = source_slot
                other.save()
            disk.slot = target_slot
            disk.save()

        if other is None:
            messages.success(request, f"{disk} wurde von Slot {source_slot} nach Slot {target_slot} verschoben.")
        else:
            messages.success(request, f"Slot {source_slot} und Slot {target_slot} wurden getauscht.")
        return JsonResponse({"moved": [disk.pk] + ([other.pk] if other else [])})


class DiskReplaceView(ContentTypePermissionRequiredMixin, View):
    """Mark a disk as removed and open a pre-filled form for its successor in the same slot."""

    http_method_names = ["post"]

    def get_required_permission(self):
        return "netbox_utilities.change_disk"

    def post(self, request, pk):
        disk = get_object_or_404(Disk.objects.restrict(request.user, "change"), pk=pk)
        if not disk.occupies_slot:
            messages.warning(request, "Dieser Datenträger ist bereits ausgebaut.")
            return redirect(disk.get_absolute_url())

        previous_status = disk.status
        disk.snapshot()
        disk.status = disks.STATUS_REPLACED
        disk.removal_date = None
        disk.save()
        messages.success(request, f"{disk} wurde als ausgebaut markiert. Bitte den neuen Datenträger erfassen.")

        successor = {
            "device": disk.device_id,
            "slot": disk.slot,
            "status": disks.STATUS_SPARE if previous_status == disks.STATUS_SPARE else disks.STATUS_ACTIVE,
            "return_url": reverse("dcim:device_disks", kwargs={"pk": disk.device_id}),
        }
        for name in ("disk_type", "interface", "form_factor", "manufacturer", "model", "capacity_gb", "raid_group"):
            value = getattr(disk, f"{name}_id" if name == "raid_group" else name)
            if value not in (None, ""):
                successor[name] = value
        return redirect(f"{reverse('plugins:netbox_utilities:disk_add')}?{urlencode(successor)}")


#
# Disks
#


class DiskByDeviceView(ContentTypePermissionRequiredMixin, View):
    """All disks grouped by device in collapsible sections; the flat list stays available."""

    template_name = "netbox_utilities/disk_by_device.html"
    # Read by the global tenant filter middleware, which injects tenant_id for this filterset.
    filterset = disk_filtersets.DiskFilterSet
    devices_per_page = 50

    def get_required_permission(self):
        return "netbox_utilities.view_disk"

    def get(self, request):
        queryset = Disk.objects.restrict(request.user, "view").select_related(
            "device", "device__role", "device__tenant", "device__site", "raid_group"
        )
        params = request.GET.copy()
        params.pop("page", None)
        show_removed = params.get("removed") == "1"
        if not show_removed and not params.getlist("status"):
            queryset = queryset.filter(status__in=disks.SLOT_OCCUPYING_STATUSES)
        filterset = self.filterset(params, queryset)
        queryset = filterset.qs.order_by("device__name", "device_id", "slot", "pk")

        groups = []
        for device, device_disks in groupby(queryset, key=lambda disk: disk.device):
            device_disks = list(device_disks)
            installed = [disk for disk in device_disks if disk.occupies_slot]
            summary = disks.disk_summary(installed, 0)
            groups.append(
                {
                    "device": device,
                    "disks": device_disks,
                    "count": len(installed),
                    "raw_capacity": disks.format_capacity(summary["raw_capacity_gb"]),
                    "failed": summary["failed"],
                    "warning_count": sum(1 for disk in installed if disk.warnings),
                }
            )

        page = Paginator(groups, self.devices_per_page).get_page(request.GET.get("page"))
        query = params.urlencode()
        return render(
            request,
            self.template_name,
            {
                "page": page,
                "groups": page.object_list,
                "device_count": len(groups),
                "disk_count": sum(group["count"] for group in groups),
                "q": params.get("q", ""),
                "show_removed": show_removed,
                "warnings_only": params.get("has_warnings") == "true",
                "query": query,
                "expand_all": len(page.object_list) == 1,
            },
        )


@register_model_view(Disk, "list", path="", detail=False)
class DiskListView(generic.ObjectListView):
    queryset = Disk.objects.select_related("device", "raid_group", "tenant")
    table = disk_tables.DiskTable
    filterset = disk_filtersets.DiskFilterSet
    filterset_form = disk_forms.DiskFilterForm


@register_model_view(Disk)
class DiskView(generic.ObjectView):
    queryset = Disk.objects.select_related("device", "raid_group", "tenant")

    def get_extra_context(self, request, instance):
        slot_history = (
            Disk.objects.filter(device=instance.device, slot=instance.slot)
            .exclude(pk=instance.pk)
            .order_by("-install_date", "-pk")
        )
        return {"slot_history": slot_history}


@register_model_view(Disk, "add", detail=False)
@register_model_view(Disk, "edit")
class DiskEditView(generic.ObjectEditView):
    queryset = Disk.objects.all()
    form = disk_forms.DiskForm

    def get_return_url(self, request, obj=None):
        if obj is not None and obj.pk and obj.device_id and "return_url" not in request.GET:
            return reverse("dcim:device_disks", kwargs={"pk": obj.device_id})
        return super().get_return_url(request, obj)


@register_model_view(Disk, "delete")
class DiskDeleteView(generic.ObjectDeleteView):
    queryset = Disk.objects.all()


@register_model_view(Disk, "bulk_import", path="import", detail=False)
class DiskBulkImportView(generic.BulkImportView):
    queryset = Disk.objects.all()
    model_form = disk_forms.DiskImportForm


@register_model_view(Disk, "bulk_edit", path="edit", detail=False)
class DiskBulkEditView(generic.BulkEditView):
    queryset = Disk.objects.select_related("device", "raid_group", "tenant")
    filterset = disk_filtersets.DiskFilterSet
    table = disk_tables.DiskTable
    form = disk_forms.DiskBulkEditForm


@register_model_view(Disk, "bulk_delete", path="delete", detail=False)
class DiskBulkDeleteView(generic.BulkDeleteView):
    queryset = Disk.objects.select_related("device", "raid_group", "tenant")
    filterset = disk_filtersets.DiskFilterSet
    table = disk_tables.DiskTable


#
# RAID groups
#


@register_model_view(RAIDGroup, "list", path="", detail=False)
class RAIDGroupListView(generic.ObjectListView):
    queryset = RAIDGroup.objects.select_related("device").prefetch_related("disks")
    table = disk_tables.RAIDGroupTable
    filterset = disk_filtersets.RAIDGroupFilterSet
    filterset_form = disk_forms.RAIDGroupFilterForm


@register_model_view(RAIDGroup)
class RAIDGroupView(generic.ObjectView):
    queryset = RAIDGroup.objects.select_related("device").prefetch_related("disks")

    def get_extra_context(self, request, instance):
        usable, tolerated, error = instance.capacity
        return {
            "members_table": disk_tables.DiskTable(instance.disks.select_related("device", "tenant"), orderable=False),
            "usable_capacity": disks.format_capacity(usable) if usable else None,
            "tolerated_failures": tolerated,
            "capacity_error": error,
        }


@register_model_view(RAIDGroup, "add", detail=False)
@register_model_view(RAIDGroup, "edit")
class RAIDGroupEditView(generic.ObjectEditView):
    queryset = RAIDGroup.objects.all()
    form = disk_forms.RAIDGroupForm

    def get_return_url(self, request, obj=None):
        if obj is not None and obj.pk and obj.device_id and "return_url" not in request.GET:
            return reverse("dcim:device_disks", kwargs={"pk": obj.device_id})
        return super().get_return_url(request, obj)


@register_model_view(RAIDGroup, "delete")
class RAIDGroupDeleteView(generic.ObjectDeleteView):
    queryset = RAIDGroup.objects.all()


@register_model_view(RAIDGroup, "bulk_delete", path="delete", detail=False)
class RAIDGroupBulkDeleteView(generic.BulkDeleteView):
    queryset = RAIDGroup.objects.all()
    filterset = disk_filtersets.RAIDGroupFilterSet
    table = disk_tables.RAIDGroupTable


#
# Device type templates
#


@register_model_view(DiskBayTemplate, "list", path="", detail=False)
class DiskBayTemplateListView(generic.ObjectListView):
    queryset = DiskBayTemplate.objects.select_related("device_type", "device_type__manufacturer")
    table = disk_tables.DiskBayTemplateTable
    filterset = disk_filtersets.DiskBayTemplateFilterSet


@register_model_view(DiskBayTemplate)
class DiskBayTemplateView(generic.ObjectView):
    queryset = DiskBayTemplate.objects.select_related("device_type")


@register_model_view(DiskBayTemplate, "add", detail=False)
@register_model_view(DiskBayTemplate, "edit")
class DiskBayTemplateEditView(generic.ObjectEditView):
    queryset = DiskBayTemplate.objects.all()
    form = disk_forms.DiskBayTemplateForm


@register_model_view(DiskBayTemplate, "delete")
class DiskBayTemplateDeleteView(generic.ObjectDeleteView):
    queryset = DiskBayTemplate.objects.all()


@register_model_view(DiskBayTemplate, "bulk_delete", path="delete", detail=False)
class DiskBayTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = DiskBayTemplate.objects.all()
    filterset = disk_filtersets.DiskBayTemplateFilterSet
    table = disk_tables.DiskBayTemplateTable
