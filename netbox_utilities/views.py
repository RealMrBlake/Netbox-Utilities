from dcim.models import Device, Module
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from netbox.plugins import get_plugin_config
from tenancy.models import Tenant, TenantGroup
from utilities.views import ContentTypePermissionRequiredMixin

from .forms import BulkModuleInstallForm, UtilitiesSettingsForm
from .middleware import (
    SESSION_TENANT_GROUP_KEY,
    SESSION_TENANT_KEY,
    GlobalTenantFilterMiddleware,
)
from .models import NavigationPreference, UtilitiesSettings
from .module_installation import BulkModuleInstallError, install_modules
from .navigation_helpers import (
    SIDEBAR_WIDTH_DEFAULT,
    SIDEBAR_WIDTH_MAX,
    SIDEBAR_WIDTH_MIN,
    SIDEBAR_WIDTH_STEP,
    get_visible_menus,
    normalize_preferences,
    normalize_sidebar_width,
    update_sidebar_layout,
)
from .runtime import (
    clear_runtime_settings_cache,
    navigation_customization_enabled,
    tenant_filter_enabled,
)


def _safe_return_url(request, default_name="home"):
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse(default_name)


class BulkModuleInstallView(ContentTypePermissionRequiredMixin, View):
    template_name = "netbox_utilities/bulk_module_install.html"

    def get_required_permission(self):
        return "dcim.add_module"

    def get(self, request):
        initial_device = self._get_device(request.GET.get("device"), request.user)
        form = BulkModuleInstallForm(
            user=request.user,
            initial={"device": initial_device} if initial_device else None,
        )
        return self._render(request, form, initial_device)

    def post(self, request):
        form = BulkModuleInstallForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                installed_modules = install_modules(
                    device=form.cleaned_data["device"],
                    module_type=form.cleaned_data["module_type"],
                    module_bays=form.cleaned_data["module_bays"],
                    status=form.cleaned_data["status"],
                    replicate_components=form.cleaned_data["replicate_components"],
                    description=form.cleaned_data["description"],
                    permitted_modules=Module.objects.restrict(request.user, "add"),
                )
            except BulkModuleInstallError as error:
                form.add_error(None, str(error))
            else:
                device = form.cleaned_data["device"]
                count = len(installed_modules)
                if count == 1:
                    success_message = f"Ein Modul des Typs {form.cleaned_data['module_type']} wurde eingebaut."
                else:
                    success_message = f"{count} Module des Typs {form.cleaned_data['module_type']} wurden eingebaut."
                messages.success(request, success_message)
                return redirect("dcim:device_modulebays", pk=device.pk)

        selected_device = form.cleaned_data.get("device") if hasattr(form, "cleaned_data") else None
        if selected_device is None:
            selected_device = self._get_device(request.POST.get("device"), request.user)
        return self._render(request, form, selected_device)

    @staticmethod
    def _get_device(device_id, user):
        if not device_id:
            return None
        return Device.objects.restrict(user, "view").filter(pk=device_id).first()

    def _render(self, request, form, device):
        if device:
            return_url = reverse("dcim:device_modulebays", kwargs={"pk": device.pk})
        else:
            return_url = reverse("dcim:module_list")
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "return_url": return_url,
            },
        )


class NavigationPreferencesView(LoginRequiredMixin, View):
    template_name = "netbox_utilities/navigation_preferences.html"

    def get(self, request):
        return self._render(request)

    def post(self, request):
        if not navigation_customization_enabled():
            return HttpResponseBadRequest("Die Navigationspersonalisierung ist deaktiviert.")

        preference, _ = NavigationPreference.objects.get_or_create(user=request.user)
        if "reset" in request.POST:
            preference.menu_order = []
            preference.hidden_menus = []
            preference.sidebar_collapsed = False
            preference.sidebar_width = SIDEBAR_WIDTH_DEFAULT
        else:
            descriptors = get_visible_menus(request.user)
            available_keys = [item["key"] for item in descriptors]
            order, hidden = normalize_preferences(
                request.POST.getlist("menu_order"),
                request.POST.getlist("hidden_menus"),
                available_keys,
            )
            preference.menu_order = order
            preference.hidden_menus = hidden
            preference.sidebar_collapsed = request.POST.get("sidebar_collapsed") == "on"
            preference.sidebar_width = normalize_sidebar_width(request.POST.get("sidebar_width"))
        preference.save()
        messages.success(request, "Die persönliche Navigation wurde gespeichert.")
        return redirect("plugins:netbox_utilities:navigation_preferences")

    def _render(self, request):
        descriptors = get_visible_menus(request.user)
        preference = NavigationPreference.objects.filter(user=request.user).first()
        order, hidden = normalize_preferences(
            preference.menu_order if preference else [],
            preference.hidden_menus if preference else [],
            [item["key"] for item in descriptors],
        )
        by_key = {item["key"]: item for item in descriptors}
        menus = [{**by_key[key], "hidden": key in hidden} for key in order]
        return render(
            request,
            self.template_name,
            {
                "menus": menus,
                "feature_enabled": navigation_customization_enabled(),
                "sidebar_collapsed": preference.sidebar_collapsed if preference else False,
                "sidebar_width": normalize_sidebar_width(
                    preference.sidebar_width if preference else SIDEBAR_WIDTH_DEFAULT
                ),
                "sidebar_width_min": SIDEBAR_WIDTH_MIN,
                "sidebar_width_max": SIDEBAR_WIDTH_MAX,
                "sidebar_width_step": SIDEBAR_WIDTH_STEP,
            },
        )


class NavigationLayoutView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        if not navigation_customization_enabled():
            return HttpResponseBadRequest("Die Navigationspersonalisierung ist deaktiviert.")

        preference, _ = NavigationPreference.objects.get_or_create(user=request.user)
        try:
            collapsed, width = update_sidebar_layout(
                preference.sidebar_collapsed,
                preference.sidebar_width,
                request.POST.get("action"),
            )
        except ValueError as error:
            return HttpResponseBadRequest(str(error))

        preference.sidebar_collapsed = collapsed
        preference.sidebar_width = width
        preference.save(update_fields=("sidebar_collapsed", "sidebar_width", "updated"))
        return JsonResponse({"collapsed": collapsed, "width": width})


class UtilitiesSettingsView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = "netbox_utilities/settings.html"
    raise_exception = True

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        instance, _ = UtilitiesSettings.objects.get_or_create(singleton_id=1)
        tenant_filter_locked = not get_plugin_config("netbox_utilities", "tenant_filter_enabled")
        tenant_required_locked = not get_plugin_config("netbox_utilities", "tenant_required")
        return render(
            request,
            self.template_name,
            {
                "form": UtilitiesSettingsForm(
                    instance=instance,
                    tenant_filter_locked=tenant_filter_locked,
                    tenant_required_locked=tenant_required_locked,
                ),
                "tenant_filter_locked": tenant_filter_locked,
                "tenant_required_locked": tenant_required_locked,
            },
        )

    def post(self, request):
        instance, _ = UtilitiesSettings.objects.get_or_create(singleton_id=1)
        form = UtilitiesSettingsForm(
            request.POST,
            instance=instance,
            tenant_filter_locked=not get_plugin_config("netbox_utilities", "tenant_filter_enabled"),
            tenant_required_locked=not get_plugin_config("netbox_utilities", "tenant_required"),
        )
        if form.is_valid():
            form.save()
            clear_runtime_settings_cache()
            if not tenant_filter_enabled():
                GlobalTenantFilterMiddleware.clear_scope(request)
            messages.success(request, "Die Plugin-Einstellungen wurden gespeichert.")
            return redirect("plugins:netbox_utilities:settings")
        return render(request, self.template_name, {"form": form})


class SelectTenantView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        if not tenant_filter_enabled():
            return HttpResponseBadRequest("Der globale Mandantenfilter ist deaktiviert.")

        scope_value = request.POST.get("scope") or request.POST.get("tenant", "")
        if not scope_value:
            GlobalTenantFilterMiddleware.clear_scope(request)
            messages.success(request, "Der globale Mandantenfilter wurde aufgehoben.")
            return redirect(_safe_return_url(request))

        if ":" in scope_value:
            scope_kind, object_id = scope_value.split(":", 1)
        else:
            scope_kind, object_id = "tenant", scope_value

        if scope_kind == "tenant":
            tenant = Tenant.objects.restrict(request.user, "view").filter(pk=object_id).first()
            if tenant is None:
                return HttpResponseBadRequest("Unbekannter oder nicht erlaubter Mandant.")
            request.session.pop(SESSION_TENANT_GROUP_KEY, None)
            request.session[SESSION_TENANT_KEY] = tenant.pk
            messages.success(request, f"Globaler Mandantenfilter: {tenant}")
        elif scope_kind == "group":
            group = TenantGroup.objects.restrict(request.user, "view").filter(pk=object_id).first()
            if group is None:
                return HttpResponseBadRequest("Unbekannte oder nicht erlaubte Mandantengruppe.")
            request.session.pop(SESSION_TENANT_KEY, None)
            request.session[SESSION_TENANT_GROUP_KEY] = group.pk
            messages.success(request, f"Globale Mandantengruppe: {group}")
        else:
            return HttpResponseBadRequest("Ungültiger Mandantenfilter.")

        return redirect(_safe_return_url(request))
