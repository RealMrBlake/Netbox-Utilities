from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from netbox.plugins import get_plugin_config
from tenancy.models import Tenant

from .forms import UtilitiesSettingsForm
from .middleware import SESSION_TENANT_KEY
from .models import NavigationPreference, UtilitiesSettings
from .navigation_helpers import get_visible_menus, normalize_preferences
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
            },
        )


class UtilitiesSettingsView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = "netbox_utilities/settings.html"
    raise_exception = True

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        instance, _ = UtilitiesSettings.objects.get_or_create(singleton_id=1)
        return render(
            request,
            self.template_name,
            {
                "form": UtilitiesSettingsForm(instance=instance),
                "config_forces_disabled": not get_plugin_config("netbox_utilities", "tenant_filter_enabled"),
            },
        )

    def post(self, request):
        if not get_plugin_config("netbox_utilities", "tenant_filter_enabled"):
            return HttpResponseBadRequest("Der Mandantenfilter ist in PLUGINS_CONFIG deaktiviert.")
        instance, _ = UtilitiesSettings.objects.get_or_create(singleton_id=1)
        form = UtilitiesSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            clear_runtime_settings_cache()
            if not form.cleaned_data["tenant_filter_enabled"]:
                request.session.pop(SESSION_TENANT_KEY, None)
            messages.success(request, "Die Plugin-Einstellungen wurden gespeichert.")
            return redirect("plugins:netbox_utilities:settings")
        return render(request, self.template_name, {"form": form})


class SelectTenantView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        if not tenant_filter_enabled():
            return HttpResponseBadRequest("Der globale Mandantenfilter ist deaktiviert.")

        tenant_id = request.POST.get("tenant")
        if tenant_id:
            tenant = Tenant.objects.restrict(request.user, "view").filter(pk=tenant_id).first()
            if tenant is None:
                return HttpResponseBadRequest("Unbekannter oder nicht erlaubter Mandant.")
            request.session[SESSION_TENANT_KEY] = tenant.pk
            messages.success(request, f"Globaler Mandantenfilter: {tenant}")
        else:
            request.session.pop(SESSION_TENANT_KEY, None)
            messages.success(request, "Der globale Mandantenfilter wurde aufgehoben.")

        return redirect(_safe_return_url(request))
