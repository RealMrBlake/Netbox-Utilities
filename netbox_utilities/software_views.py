"""Client software overview and the device "Software" tab, based on netbox-slm installations."""

import csv

from dcim.models import Device, DeviceRole
from django import forms
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from netbox.views import generic
from tenancy.models import Tenant, TenantGroup
from utilities.forms.fields import DynamicModelMultipleChoiceField
from utilities.views import ContentTypePermissionRequiredMixin, ViewTab, register_model_view

from . import software
from .tenant_scope import active_tenant_scope

INSTALLATION_PERMISSION = "netbox_slm.view_softwareproductinstallation"

ROW_FIELDS = {
    "product_id": "software_product_id",
    "product_name": "software_product__name",
    "manufacturer": "software_product__manufacturer__name",
    "version_id": "version_id",
    "version_name": "version__name",
    "end_of_support": "version__end_of_support",
    "release_type": "version__release_type",
    "device_id": "device_id",
}


def installation_model():
    from netbox_slm.models import SoftwareProductInstallation

    return SoftwareProductInstallation


def client_role_ids():
    roles = software.configured_roles()
    return [role.pk for role in DeviceRole.objects.all() if role.name.casefold() in roles]


class SoftwareOverviewFilterForm(forms.Form):
    tenant_group_id = DynamicModelMultipleChoiceField(
        queryset=TenantGroup.objects.all(), required=False, label="Mandantengruppe"
    )
    tenant_id = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label="Mandant",
        query_params={"group_id": "$tenant_group_id"},
    )
    role_id = DynamicModelMultipleChoiceField(queryset=DeviceRole.objects.all(), required=False, label="Gerätrolle")
    q = forms.CharField(required=False, label="Software suchen")


def group_tenant_ids(groups):
    group_ids = set()
    for group in groups:
        group_ids.update(group.get_descendants(include_self=True).values_list("pk", flat=True))
    return set(Tenant.objects.filter(group_id__in=group_ids).values_list("pk", flat=True))


class SoftwareOverviewView(ContentTypePermissionRequiredMixin, View):
    """Software products, versions and the clients they are installed on, per tenant or tenant group."""

    template_name = "netbox_utilities/software_overview.html"

    def get_required_permission(self):
        return INSTALLATION_PERMISSION

    def get(self, request):
        params = request.GET.copy()
        submitted = params.pop("submitted", None) is not None
        if not submitted and "role_id" not in params:
            # First visit: clients only. An emptied role field afterwards means all roles.
            params.setlist("role_id", [str(pk) for pk in client_role_ids()])
        form = SoftwareOverviewFilterForm(params)
        form.is_valid()
        data = getattr(form, "cleaned_data", {})

        devices = Device.objects.restrict(request.user, "view")
        tenant_ids, scope_label = self.selected_tenant_ids(request, data)
        if tenant_ids is not None:
            devices = devices.filter(tenant_id__in=tenant_ids)
        if roles := data.get("role_id"):
            devices = devices.filter(role__in=roles)

        installations = (
            installation_model()
            .objects.restrict(request.user, "view")
            .filter(device__isnull=False, device__in=devices)
        )
        if q := (data.get("q") or "").strip():
            installations = installations.filter(
                Q(software_product__name__icontains=q)
                | Q(software_product__manufacturer__name__icontains=q)
                | Q(version__name__icontains=q)
            )

        product_id = _int(params.get("product"))
        version_id = _int(params.get("version"))
        if params.get("export") == "csv":
            if product_id:
                installations = installations.filter(software_product_id=product_id)
            if version_id:
                installations = installations.filter(version_id=version_id)
            return csv_response(installations)

        rows = [
            {key: row[path] for key, path in ROW_FIELDS.items()}
            for row in installations.values(*ROW_FIELDS.values())
        ]
        summary = software.summarize(rows, device_total=devices.count())
        filter_query = _query(params, drop=("product", "version", "export"))
        context = {
            "form": form,
            "summary": summary,
            "scope_label": scope_label,
            "filter_query": filter_query,
            "today": timezone.localdate(),
            "can_add": request.user.has_perm("netbox_slm.add_softwareproductinstallation"),
        }
        if product_id:
            product = next((item for item in summary.products if item.id == product_id), None)
            context.update(product_context(request, installations, product, version_id))
        return render(request, self.template_name, context)

    @staticmethod
    def selected_tenant_ids(request, data):
        """Tenant ids to filter by (None = all) and a label if the global tenant filter applies."""
        tenants, groups = data.get("tenant_id"), data.get("tenant_group_id")
        if tenants or groups:
            ids = {tenant.pk for tenant in tenants or ()}
            if groups:
                ids |= group_tenant_ids(groups)
            return ids, None
        scope = active_tenant_scope.get()
        if scope is None:
            return None, None
        selected = getattr(request, "netbox_utilities_tenant_group", None) or getattr(
            request, "netbox_utilities_tenant", None
        )
        return set(scope.tenant_ids), str(selected) if selected else "aktiv"


def product_context(request, installations, product, version_id):
    """Drill-down of one product: its versions and the devices it is installed on."""
    if product is None:
        return {"product_missing": True}
    selected = product.versions.get(version_id) if version_id else None
    queryset = installations.filter(software_product_id=product.id)
    if selected:
        queryset = queryset.filter(version_id=selected.id)
    entries = sorted(
        queryset.select_related("device", "device__tenant", "device__site", "device__role", "version"),
        key=lambda entry: (entry.device.name or "").casefold(),
    )
    return {
        "product": product,
        "product_obj": product_object(request, product.id),
        "selected_version": selected,
        "entries": entries,
    }


def product_object(request, product_id):
    from netbox_slm.models import SoftwareProduct

    return SoftwareProduct.objects.restrict(request.user, "view").filter(pk=product_id).first()


def csv_response(installations):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="client-software.csv"'
    response.write("﻿")  # Excel recognises UTF-8 with BOM
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Mandant", "Rechner", "Rolle", "Standort", "Hersteller", "Software", "Version", "Support-Ende"])
    queryset = installations.select_related(
        "device__tenant", "device__role", "device__site", "software_product__manufacturer", "version"
    ).order_by("device__tenant__name", "device__name", "software_product__name")
    for entry in queryset:
        device = entry.device
        writer.writerow(
            [
                device.tenant or "",
                device.name or "",
                device.role or "",
                device.site or "",
                entry.software_product.manufacturer or "",
                entry.software_product,
                entry.version,
                entry.version.end_of_support or "",
            ]
        )
    return response


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _query(params, drop=()):
    params = params.copy()
    for key in drop:
        params.pop(key, None)
    params["submitted"] = "1"
    return params.urlencode()


#
# Device tab
#


def software_tab_badge(device):
    """Number of installations; hidden for devices without client role and without software."""
    from .runtime import software_enabled

    if not software_enabled():
        return None
    count = installation_model().objects.filter(device=device).count()
    if count:
        return str(count)
    return "0" if software.supports_software(device) else None


@register_model_view(Device, "software", path="software")
class DeviceSoftwareTabView(generic.ObjectView):
    queryset = Device.objects.all()
    template_name = "netbox_utilities/device_software.html"
    tab = ViewTab(
        label="Software",
        badge=software_tab_badge,
        permission=INSTALLATION_PERMISSION,
        weight=2070,
        hide_if_empty=True,
    )

    def get_extra_context(self, request, instance):
        entries = sorted(
            installation_model()
            .objects.restrict(request.user, "view")
            .filter(device=instance)
            .select_related("software_product", "software_product__manufacturer", "version"),
            key=lambda entry: (entry.software_product.name.casefold(), software.version_key(entry.version.name)),
        )
        tab_url = reverse("dcim:device_software", kwargs={"pk": instance.pk})
        overview_url = reverse("plugins:netbox_utilities:software_overview")
        if instance.tenant_id:
            overview_url += f"?submitted=1&tenant_id={instance.tenant_id}"
        return {
            "entries": entries,
            "today": timezone.localdate(),
            "supported": software.supports_software(instance),
            "tab_url": tab_url,
            "overview_url": overview_url,
            "add_url": f"{reverse('plugins:netbox_slm:softwareproductinstallation_add')}?device={instance.pk}"
            f"&return_url={tab_url}",
            "can_add": request.user.has_perm("netbox_slm.add_softwareproductinstallation"),
            "can_change": request.user.has_perm("netbox_slm.change_softwareproductinstallation"),
            "can_delete": request.user.has_perm("netbox_slm.delete_softwareproductinstallation"),
        }
