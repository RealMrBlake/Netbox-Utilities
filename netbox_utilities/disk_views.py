import base64
from datetime import timedelta
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
from django.utils import timezone
from django.views import View
from netbox.plugins import get_plugin_config
from netbox.views import generic
from utilities.views import ContentTypePermissionRequiredMixin, ViewTab, register_model_view

from . import disk_filtersets, disk_forms, disk_tables, disks, msa_import
from .models import DEFAULT_BAY_NAME, Disk, DiskBayLayout, DiskBayTemplate, RAIDGroup

BAY_NAME_SUGGESTIONS = ("Front", "Rückseite", "Intern", "BOSS-Karte (M.2)", "PCIe", "M.2")


def disk_tab_badge(device):
    """Number of installed disks; None hides the tab for roles without disks.

    The count is returned as a string so that "0" still shows the tab (hide_if_empty).
    """
    if not get_plugin_config("netbox_utilities", "disks_enabled") or not disks.supports_disks(device):
        return None
    return str(Disk.objects.filter(device=device, status__in=disks.SLOT_OCCUPYING_STATUSES).count())


def device_disk_context(device):
    bays = list(DiskBayLayout.objects.filter(device=device).order_by("weight", "name", "pk"))
    device_disks = list(
        Disk.objects.filter(device=device)
        .select_related("raid_group", "bay")
        .order_by("bay__weight", "bay__name", "slot", "-removal_date", "pk")
    )
    installed = [disk for disk in device_disks if disk.occupies_slot]
    history = [disk for disk in device_disks if not disk.occupies_slot]
    raid_groups = list(RAIDGroup.objects.filter(device=device).prefetch_related("disks"))
    templates = list(DiskBayTemplate.objects.filter(device_type_id=device.device_type_id).order_by("weight", "name"))
    context = {
        "supported": disks.supports_disks(device),
        "bays": bays,
        "raid_groups": raid_groups,
        "history_table": disk_tables.DeviceDiskHistoryTable(history, orderable=False),
        "history_count": len(history),
        "disk_warnings": [(disk, disk.warnings) for disk in installed if disk.warnings],
        "device_type_templates": templates,
    }
    if not bays:
        context["setup_form"] = disk_forms.DiskBayLayoutForm(initial={"name": DEFAULT_BAY_NAME})
        return context

    bay_sections = []
    placed = set()
    for bay in bays:
        by_slot = {
            disk.slot: disk
            for disk in installed
            if disk.bay_id == bay.pk and bay.first_slot <= disk.slot <= bay.last_slot
        }
        placed.update(disk.pk for disk in by_slot.values())
        bay_sections.append(
            {
                "bay": bay,
                "grid": disks.build_slot_grid(bay.slot_count, bay.rows, bay.first_slot, bay.numbering, by_slot),
                "used": len(by_slot),
                "free": bay.slot_count - len(by_slot),
            }
        )

    usable = [group.usable_capacity_gb for group in raid_groups if group.usable_capacity_gb]
    summary = disks.disk_summary(installed, sum(bay.slot_count for bay in bays))
    summary.update(
        {
            "raw_capacity": disks.format_capacity(summary["raw_capacity_gb"]),
            "usable_capacity": disks.format_capacity(sum(usable)) if usable else None,
            "degraded_groups": sum(1 for group in raid_groups if group.is_degraded),
        }
    )
    context.update(
        {
            "bay_sections": bay_sections,
            "summary": summary,
            "orphaned_disks": [disk for disk in installed if disk.pk not in placed],
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
    def get_bay(device, bay_id):
        """The requested area of the device, or its first area when none is given."""
        bays = DiskBayLayout.objects.filter(device=device).order_by("weight", "name", "pk")
        if bay_id not in (None, ""):
            return get_object_or_404(bays, pk=bay_id)
        return bays.first()

    @staticmethod
    def tab_url(device):
        return reverse("dcim:device_disks", kwargs={"pk": device.pk})


class DeviceDiskSetupView(_DeviceDiskActionView):
    """Create, change or delete a slot area ("Bereich") of a device; also applies device type templates."""

    template_name = "netbox_utilities/device_disk_setup.html"

    def get(self, request, pk):
        device = self.get_device(request, pk)
        bay = self.get_bay(device, request.GET.get("bay")) if request.GET.get("bay") else None
        has_bays = DiskBayLayout.objects.filter(device=device).exists()
        initial = {"save_as_template": True}
        if bay is None:
            initial["name"] = "" if has_bays else DEFAULT_BAY_NAME
            initial["weight"] = 200 if has_bays else 100
        form = disk_forms.DiskBayLayoutForm(instance=bay, initial=initial)
        return self._render(request, device, form, bay)

    def post(self, request, pk):
        device = self.get_device(request, pk)

        if "apply_template" in request.POST:
            templates = DiskBayTemplate.objects.filter(device_type_id=device.device_type_id)
            existing = set(DiskBayLayout.objects.filter(device=device).values_list("name", flat=True))
            created = [
                DiskBayLayout.objects.create(device=device, **template.layout_values())
                for template in templates
                if template.name not in existing
            ]
            if created:
                names = ", ".join(bay.name for bay in created)
                messages.success(request, f"Bereiche aus der Vorlage übernommen: {names}.")
            else:
                messages.info(request, "Alle Bereiche der Vorlage sind bereits vorhanden.")
            return redirect(self.tab_url(device))

        bay = self.get_bay(device, request.POST.get("bay")) if request.POST.get("bay") else None

        if "delete" in request.POST and bay is not None:
            if Disk.objects.filter(bay=bay, status__in=disks.SLOT_OCCUPYING_STATUSES).exists():
                messages.error(request, f"Der Bereich {bay.name} ist noch bestückt und kann nicht gelöscht werden.")
                return redirect(self.tab_url(device))
            with transaction.atomic():
                # Removed disks keep their history, only without the deleted area.
                for disk in Disk.objects.filter(bay=bay):
                    disk.snapshot()
                    disk.bay = None
                    disk.save()
                bay.delete()
            messages.success(request, f"Der Bereich {bay.name} wurde gelöscht.")
            return redirect(self.tab_url(device))

        if bay is not None:
            bay.snapshot()
        form = disk_forms.DiskBayLayoutForm(request.POST, instance=bay or DiskBayLayout(device=device))
        if form.is_valid():
            first_bay = not DiskBayLayout.objects.filter(device=device).exclude(pk=bay.pk if bay else None).exists()
            bay = form.save()
            if first_bay:
                # Disks recorded before the device had any area belong to its first one.
                for disk in Disk.objects.filter(device=device, bay__isnull=True):
                    disk.snapshot()
                    disk.bay = bay
                    disk.save()
            if form.cleaned_data.get("save_as_template"):
                values = bay.layout_values()
                DiskBayTemplate.objects.update_or_create(
                    device_type_id=device.device_type_id,
                    name=values.pop("name"),
                    defaults=values,
                )
            messages.success(request, f"Bereich {bay.name} mit {bay.slot_count} Steckplätzen gespeichert.")
            return redirect(self.tab_url(device))
        return self._render(request, device, form, bay)

    def _render(self, request, device, form, bay):
        return render(
            request,
            self.template_name,
            {
                "object": device,
                "form": form,
                "bay": bay,
                "bay_names": BAY_NAME_SUGGESTIONS,
                "can_delete": bay is not None
                and not Disk.objects.filter(bay=bay, status__in=disks.SLOT_OCCUPYING_STATUSES).exists(),
            },
        )


class DeviceDiskBulkFillView(_DeviceDiskActionView):
    template_name = "netbox_utilities/device_disk_fill.html"

    @staticmethod
    def free_slots(bay):
        used = set(
            Disk.objects.filter(bay=bay, status__in=disks.SLOT_OCCUPYING_STATUSES).values_list("slot", flat=True)
        )
        return [slot for slot in range(bay.first_slot, bay.last_slot + 1) if slot not in used]

    def get(self, request, pk):
        device = self.get_device(request, pk)
        bay = self.get_bay(device, request.GET.get("bay"))
        if bay is None:
            return redirect(self.tab_url(device))
        free = self.free_slots(bay)
        selected = [int(slot) for slot in request.GET.getlist("slots") if slot.isdigit()]
        initial = {
            "slots": [slot for slot in selected if slot in free] or free,
            "form_factor": bay.form_factor,
        }
        form = disk_forms.DiskBulkFillForm(bay=bay, free_slots=free, initial=initial)
        return self._render(request, device, bay, form, free)

    def post(self, request, pk):
        device = self.get_device(request, pk)
        bay = self.get_bay(device, request.POST.get("bay"))
        if bay is None:
            return redirect(self.tab_url(device))
        free = self.free_slots(bay)
        form = disk_forms.DiskBulkFillForm(request.POST, bay=bay, free_slots=free)
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
                messages.success(request, f"{len(new_disks)} Datenträger wurden in {bay.name} eingebaut.")
                return redirect(self.tab_url(device))
        return self._render(request, device, bay, form, free)

    def _render(self, request, device, bay, form, free):
        return render(
            request,
            self.template_name,
            {"object": device, "bay": bay, "form": form, "free_slots": free, "return_url": self.tab_url(device)},
        )


# Parking slot while two disks swap places; the unique (bay, slot) constraint
# would otherwise reject the intermediate state.
SWAP_PARKING_SLOT = 32767


class DeviceDiskMoveView(ContentTypePermissionRequiredMixin, View):
    """Drag and drop on the slot grid: move a disk to a free slot or swap two disks, also across areas."""

    http_method_names = ["post"]

    def get_required_permission(self):
        return "netbox_utilities.change_disk"

    def post(self, request, pk):
        device = get_object_or_404(Device.objects.restrict(request.user, "view"), pk=pk)
        installed = Disk.objects.restrict(request.user, "change").filter(
            device=device, status__in=disks.SLOT_OCCUPYING_STATUSES
        )
        try:
            disk = installed.select_related("bay").get(pk=int(request.POST.get("disk", "")))
            target_bay = DiskBayLayout.objects.get(device=device, pk=int(request.POST.get("bay", "")))
            target_slot = int(request.POST.get("slot", ""))
        except (ValueError, Disk.DoesNotExist, DiskBayLayout.DoesNotExist):
            return JsonResponse({"error": "Unbekannter Datenträger, Bereich oder Steckplatz."}, status=400)
        if not target_bay.first_slot <= target_slot <= target_bay.last_slot:
            return JsonResponse({"error": f"{target_bay.name} hat keinen Steckplatz {target_slot}."}, status=400)
        if target_bay.pk == disk.bay_id and target_slot == disk.slot:
            return JsonResponse({"moved": []})

        source_bay, source_slot, source_label = disk.bay, disk.slot, disk.slot_label
        with transaction.atomic():
            other = (
                Disk.objects.select_for_update()
                .filter(bay=target_bay, slot=target_slot, status__in=disks.SLOT_OCCUPYING_STATUSES)
                .first()
            )
            if other is not None and not installed.filter(pk=other.pk).exists():
                return JsonResponse({"error": "Keine Berechtigung für den Datenträger im Ziel."}, status=403)

            disk.snapshot()
            if other is not None:
                other.snapshot()
                disk.slot = SWAP_PARKING_SLOT
                disk.save()
                other.bay, other.slot = source_bay, source_slot
                other.save()
            disk.bay, disk.slot = target_bay, target_slot
            disk.save()

        if other is None:
            messages.success(request, f"{disk} wurde von {source_label} nach {disk.slot_label} verschoben.")
        else:
            messages.success(request, f"{source_label} und {disk.slot_label} wurden getauscht.")
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
            "bay": disk.bay_id,
            "slot": disk.slot,
            "status": disks.STATUS_SPARE if previous_status == disks.STATUS_SPARE else disks.STATUS_ACTIVE,
            "return_url": reverse("dcim:device_disks", kwargs={"pk": disk.device_id}),
        }
        if successor["bay"] is None:
            del successor["bay"]
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
            "device", "device__role", "device__tenant", "device__site", "raid_group", "bay"
        )
        params = request.GET.copy()
        params.pop("page", None)
        show_removed = params.get("removed") == "1"
        if not show_removed and not params.getlist("status"):
            queryset = queryset.filter(status__in=disks.SLOT_OCCUPYING_STATUSES)
        filterset = self.filterset(params, queryset)
        queryset = filterset.qs.order_by("device__name", "device_id", "bay__weight", "bay__name", "slot", "pk")

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
    queryset = Disk.objects.select_related("device", "bay", "raid_group", "tenant")
    table = disk_tables.DiskTable
    filterset = disk_filtersets.DiskFilterSet
    filterset_form = disk_forms.DiskFilterForm


@register_model_view(Disk)
class DiskView(generic.ObjectView):
    queryset = Disk.objects.select_related("device", "bay", "raid_group", "tenant")

    def get_extra_context(self, request, instance):
        slot_history = (
            Disk.objects.filter(device=instance.device, bay=instance.bay, slot=instance.slot)
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
    queryset = Disk.objects.select_related("device", "bay", "raid_group", "tenant")
    filterset = disk_filtersets.DiskFilterSet
    table = disk_tables.DiskTable
    form = disk_forms.DiskBulkEditForm


@register_model_view(Disk, "bulk_delete", path="delete", detail=False)
class DiskBulkDeleteView(generic.BulkDeleteView):
    queryset = Disk.objects.select_related("device", "bay", "raid_group", "tenant")
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


#
# HPE MSA import
#

IMPORTING_ACTIONS = (msa_import.ACTION_NEW, msa_import.ACTION_UPDATE, msa_import.ACTION_REPLACE)


class MSADiskImportView(ContentTypePermissionRequiredMixin, View):
    """Import the disk CSV export of an HPE MSA: map each enclosure (shelf) to a device, preview, create.

    The wizard keeps no server-side state; the export travels base64-encoded in a hidden field.
    """

    template_name = "netbox_utilities/disk_msa_import.html"

    def get_required_permission(self):
        return "netbox_utilities.add_disk"

    def get(self, request):
        return self._render(request, "upload", upload_form=disk_forms.MSAUploadForm())

    def post(self, request):
        step = request.POST.get("step", "upload")
        if step == "upload" or not request.POST.get("export_data"):
            upload_form = disk_forms.MSAUploadForm(request.POST, request.FILES)
            if not upload_form.is_valid():
                return self._render(request, "upload", upload_form=upload_form)
            raw = upload_form.cleaned_data["raw"]
            export = upload_form.cleaned_data["export"]
            return self._render_assign(request, raw, export, self._assign_form(request, export))

        try:
            raw = base64.b64decode(request.POST["export_data"]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            messages.error(request, "Die Importdaten waren beschädigt. Bitte die Datei erneut hochladen.")
            return redirect("plugins:netbox_utilities:disk_msa_import")
        export = msa_import.parse_export(raw)
        assign_form = self._assign_form(request, export, data=request.POST)
        if step == "back" or not assign_form.is_valid():
            return self._render_assign(request, raw, export, assign_form)

        bound = step == "plan"
        plans = [
            self._plan_enclosure(request, enclosure, device, export.enclosures[enclosure], assign_form, bound)
            for enclosure, device in assign_form.cleaned_data["assigned"].items()
        ]
        if bound and "do_import" in request.POST:
            error = self._import_blocker(request, plans)
            if error:
                messages.error(request, error)
            else:
                try:
                    summary = self._execute(request, plans, assign_form.cleaned_data)
                except ValidationError as exc:
                    for message in exc.messages:
                        messages.error(request, message)
                else:
                    messages.success(request, summary)
                    devices = [plan["device"] for plan in plans]
                    if len(devices) == 1:
                        return redirect("dcim:device_disks", pk=devices[0].pk)
                    return redirect(
                        f"{reverse('plugins:netbox_utilities:disk_by_device')}?"
                        + urlencode([("device_id", device.pk) for device in devices])
                    )
        return self._render(
            request,
            "plan",
            export_data=self._encode(raw),
            assign_form=assign_form,
            plans=plans,
            parse_errors=export.errors,
        )

    @staticmethod
    def _encode(raw):
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    @staticmethod
    def _assign_form(request, export, data=None):
        form = disk_forms.MSAAssignForm(data, enclosures=list(export.enclosures))
        devices = Device.objects.restrict(request.user, "view")
        for enclosure in form.enclosures:
            form.fields[f"device_{enclosure}"].queryset = devices
        return form

    def _render_assign(self, request, raw, export, assign_form):
        enclosures = [
            {
                "id": enclosure,
                "field": assign_form[f"device_{enclosure}"],
                "count": len(items),
                "first": items[0].slot,
                "last": items[-1].slot,
                "models": sorted({item.model for item in items if item.model}),
            }
            for enclosure, items in export.enclosures.items()
        ]
        return self._render(
            request,
            "assign",
            export_data=self._encode(raw),
            assign_form=assign_form,
            enclosures=enclosures,
            parse_errors=export.errors,
        )

    @staticmethod
    def _bay_defaults(device, items):
        """Initial values for a new slot area: the device type template, else a guess from the export."""
        templates = DiskBayTemplate.objects.filter(device_type_id=device.device_type_id).order_by("weight", "name")
        template = templates.first()
        if template is not None:
            values = template.layout_values()
        else:
            first = 0 if min(item.slot for item in items) == 0 else 1
            count = msa_import.suggest_slot_count(max(item.slot for item in items) - first + 1)
            values = {
                "name": DEFAULT_BAY_NAME,
                "weight": 100,
                "slot_count": count,
                "rows": 1,
                "first_slot": first,
                "numbering": disks.NUMBERING_HORIZONTAL,
                "form_factor": msa_import.suggest_form_factor(count),
            }
        values["save_as_template"] = template is None
        return values

    def _plan_enclosure(self, request, enclosure, device, items, assign_form, bound):
        bays = list(DiskBayLayout.objects.filter(device=device).order_by("weight", "name", "pk"))
        bay = bay_form = None
        if bays:
            requested = request.POST.get(f"bay_{enclosure}") if bound else None
            bay = next((item for item in bays if str(item.pk) == requested), None)
            if bay is None:
                highest = max(item.slot for item in items)
                bay = next((item for item in bays if item.first_slot <= highest <= item.last_slot), bays[0])
            first_slot, last_slot = bay.first_slot, bay.last_slot
        else:
            # The device has no slots yet: ask for the area right here, pre-filled from the export.
            defaults = self._bay_defaults(device, items)
            bay_form = disk_forms.DiskBayLayoutForm(
                request.POST if bound else None,
                prefix=f"bay{enclosure}",
                instance=DiskBayLayout(device=device),
                initial=defaults,
            )
            bay_form.fields["slot_count"].widget.attrs.pop("autofocus", None)
            if bound and bay_form.is_valid():
                first_slot = bay_form.cleaned_data["first_slot"]
                slot_count = bay_form.cleaned_data["slot_count"]
            else:
                first_slot, slot_count = defaults["first_slot"], defaults["slot_count"]
            last_slot = first_slot + slot_count - 1

        # Disks in the chosen area, or without area while the device has none yet.
        installed = Disk.objects.filter(device=device, status__in=disks.SLOT_OCCUPYING_STATUSES)
        installed = installed.filter(bay=bay) if bay is not None else installed.filter(bay__isnull=True)
        occupants = {disk.slot: disk for disk in installed}
        holders = {}
        serials = [item.serial for item in items if item.serial]
        for disk in Disk.objects.filter(serial__in=serials, status__in=disks.SLOT_OCCUPYING_STATUSES).select_related(
            "device", "bay"
        ):
            holders.setdefault(disk.serial.casefold(), []).append(disk)

        replace = assign_form.cleaned_data["replace_existing"]
        rows = []
        for item in items:
            occupant = occupants.get(item.slot)
            elsewhere = next(
                (
                    f"{disk.device} – {disk.slot_label}"
                    for disk in holders.get(item.serial.casefold(), [])
                    if occupant is None or disk.pk != occupant.pk
                ),
                None,
            )
            action, reason = msa_import.classify(
                item,
                first_slot,
                last_slot,
                occupant_serial=None if occupant is None else occupant.serial,
                serial_elsewhere=elsewhere,
                replace=replace,
            )
            label, color = msa_import.ACTION_LABELS[action]
            rows.append(
                {
                    "item": item,
                    "occupant": occupant,
                    "action": action,
                    "label": label,
                    "color": color,
                    "reason": reason,
                    "capacity": disks.format_capacity(item.capacity_gb),
                }
            )
        return {
            "enclosure": enclosure,
            "device": device,
            "bays": bays,
            "bay": bay,
            "bay_form": bay_form,
            "rows": rows,
            "importing": sum(1 for row in rows if row["action"] in IMPORTING_ACTIONS),
            "groups": sorted({item.disk_group for item in items if item.disk_group}),
        }

    @staticmethod
    def _import_blocker(request, plans):
        if any(plan["bay_form"] is not None and not plan["bay_form"].is_valid() for plan in plans):
            return "Bitte die Angaben zu den neuen Steckplatz-Bereichen korrigieren."
        actions = [row["action"] for plan in plans for row in plan["rows"]]
        if not any(action in IMPORTING_ACTIONS for action in actions):
            return "Es gibt nichts zu importieren."
        changes = any(action in (msa_import.ACTION_UPDATE, msa_import.ACTION_REPLACE) for action in actions)
        if changes and not request.user.has_perm("netbox_utilities.change_disk"):
            return "Zum Aktualisieren oder Ersetzen vorhandener Datenträger fehlt die Berechtigung."
        return None

    @staticmethod
    def _execute(request, plans, options):
        today = timezone.localdate()
        may_add_groups = request.user.has_perm("netbox_utilities.add_raidgroup")
        totals = dict.fromkeys((*IMPORTING_ACTIONS, "bays", "groups"), 0)

        with transaction.atomic():
            for plan in plans:
                device, bay, bay_form = plan["device"], plan["bay"], plan["bay_form"]
                if bay_form is not None:
                    bay = bay_form.save()
                    totals["bays"] += 1
                    # Disks recorded before the device had any area belong to its first one.
                    for disk in Disk.objects.filter(device=device, bay__isnull=True):
                        disk.snapshot()
                        disk.bay = bay
                        disk.save()
                    if bay_form.cleaned_data.get("save_as_template"):
                        values = bay.layout_values()
                        DiskBayTemplate.objects.update_or_create(
                            device_type_id=device.device_type_id, name=values.pop("name"), defaults=values
                        )

                groups = {group.name.casefold(): group for group in RAIDGroup.objects.filter(device=device)}
                if options["create_raid_groups"] and may_add_groups:
                    for name in plan["groups"]:
                        if name.casefold() not in groups:
                            group = RAIDGroup(
                                device=device, name=name, level="other", description="Aus HPE MSA importiert"
                            )
                            group.full_clean()
                            group.save()
                            groups[name.casefold()] = group
                            totals["groups"] += 1

                for row in plan["rows"]:
                    item, action = row["item"], row["action"]
                    if action not in IMPORTING_ACTIONS:
                        continue
                    values = {
                        "status": item.status,
                        "disk_type": item.disk_type,
                        "interface": item.interface,
                        "manufacturer": item.manufacturer,
                        "model": item.model,
                        "capacity_gb": item.capacity_gb,
                        "firmware": item.firmware,
                        "raid_group": groups.get(item.disk_group.casefold()) if item.disk_group else None,
                    }
                    if action == msa_import.ACTION_UPDATE:
                        disk = Disk.objects.get(pk=row["occupant"].pk)
                        disk.snapshot()
                        disk.bay = bay
                        for name, value in values.items():
                            if value not in (None, "") or name == "raid_group":
                                setattr(disk, name, value)
                    else:
                        if action == msa_import.ACTION_REPLACE:
                            old = Disk.objects.get(pk=row["occupant"].pk)
                            old.snapshot()
                            old.status = disks.STATUS_REPLACED
                            old.save()
                        disk = Disk(device=device, bay=bay, slot=item.slot, serial=item.serial, **values)
                        disk.form_factor = bay.form_factor
                        if options["estimate_install_date"] and item.power_on_hours:
                            disk.install_date = today - timedelta(hours=item.power_on_hours)
                        else:
                            disk.install_date = today
                    disk.full_clean()
                    disk.save()
                    totals[action] += 1

        parts = [f"{totals[msa_import.ACTION_NEW]} neu", f"{totals[msa_import.ACTION_UPDATE]} aktualisiert"]
        if totals[msa_import.ACTION_REPLACE]:
            parts.append(f"{totals[msa_import.ACTION_REPLACE]} ersetzt")
        text = "MSA-Import abgeschlossen: " + ", ".join(parts) + "."
        if totals["bays"]:
            text += f" {totals['bays']} Steckplatz-Bereich(e) angelegt."
        if totals["groups"]:
            text += f" {totals['groups']} RAID-Gruppe(n) angelegt – bitte das RAID-Level prüfen."
        return text

    def _render(self, request, step, **context):
        return render(request, self.template_name, {"step": step, **context})
