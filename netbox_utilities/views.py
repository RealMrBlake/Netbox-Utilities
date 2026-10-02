from contextlib import contextmanager
from io import BytesIO

from dcim.models import Device, Module, Rack
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.db import DatabaseError, transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from extras.forms import ImageAttachmentForm
from extras.models import ImageAttachment
from netbox.models.features import has_feature
from netbox.plugins import get_plugin_config
from tenancy.models import Tenant, TenantGroup
from utilities.views import ContentTypePermissionRequiredMixin

from .forms import BulkImageUploadForm, BulkModuleInstallForm, UtilitiesSettingsForm
from .middleware import (
    SESSION_TENANT_GROUP_KEY,
    SESSION_TENANT_KEY,
    GlobalTenantFilterMiddleware,
)
from .models import NavigationPreference, UtilitiesSettings
from .module_installation import BulkModuleInstallError, install_modules
from .navigation_helpers import (
    SIDEBAR_WIDTH_DEFAULT,
    get_visible_menus,
    normalize_preferences,
    update_sidebar_layout,
)
from .runtime import (
    clear_runtime_settings_cache,
    navigation_customization_enabled,
    offline_svg_export_enabled,
    tenant_filter_enabled,
)
from .svg_export import RACK_VIEW_MODES, apply_rack_view_mode, strip_svg_hyperlinks


def _safe_return_url(request, default_name="home"):
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse(default_name)


# NetBox limits Pillow to 25 MP (bomb error above 50 MP), which rejects
# current 50 MP smartphone photos such as Google Pixel images (8160x6144).
BULK_IMAGE_MAX_PIXELS = 100_000_000


@contextmanager
def raised_image_pixel_limit():
    from PIL import Image

    original_limit = Image.MAX_IMAGE_PIXELS
    if original_limit is not None and original_limit < BULK_IMAGE_MAX_PIXELS:
        Image.MAX_IMAGE_PIXELS = BULK_IMAGE_MAX_PIXELS
    try:
        yield
    finally:
        Image.MAX_IMAGE_PIXELS = original_limit


class BulkImageUploadView(ContentTypePermissionRequiredMixin, View):
    template_name = "netbox_utilities/bulk_image_upload.html"

    def get_required_permission(self):
        return "extras.add_imageattachment"

    def get(self, request):
        parent = self._get_parent(request, request.GET)
        form = BulkImageUploadForm()
        return self._render(request, form, parent)

    def post(self, request):
        parent = self._get_parent(request, request.POST)
        form = BulkImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            with raised_image_pixel_limit():
                return self._process_upload(request, form, parent)
        return self._render(request, form, parent)

    def _process_upload(self, request, form, parent):
        image_forms = self._build_image_forms(parent, form.cleaned_data)
        invalid = [image_form for image_form in image_forms if not image_form.is_valid()]
        if invalid:
            for image_form in invalid:
                image = image_form.files.get("image")
                reason = self._image_error_reason(image)
                if reason:
                    form.add_error("images", f"{getattr(image, 'name', 'Bild')}: Pillow meldet: {reason}")
            for image_form in invalid:
                filename = getattr(image_form.files.get("image"), "name", "Bild")
                for errors in image_form.errors.values():
                    for error in errors:
                        form.add_error("images", f"{filename}: {error}")
        else:
            created = []
            try:
                with transaction.atomic():
                    for image_form in image_forms:
                        created.append(image_form.save())
            except (DatabaseError, OSError, SuspiciousFileOperation, ValidationError, ValueError) as error:
                for image_form in image_forms:
                    image_file = image_form.instance.image
                    if image_file.name and image_file._committed:
                        image_file.delete(save=False)
                form.add_error("images", f"Die Bilder konnten nicht gespeichert werden: {error}")
            else:
                count = len(created)
                noun = "Bild wurde" if count == 1 else "Bilder wurden"
                messages.success(request, f"{count} {noun} gleichzeitig hochgeladen.")
                return redirect(self._return_url(request, parent))
        return self._render(request, form, parent)

    @staticmethod
    def _get_parent(request, data):
        try:
            object_type_id = int(data.get("object_type", ""))
            object_id = int(data.get("object_id", ""))
        except (TypeError, ValueError):
            raise Http404("Ungültiges Zielobjekt.") from None

        object_type = get_object_or_404(ContentType, pk=object_type_id)
        model = object_type.model_class()
        if model is None or not has_feature(model, "image_attachments"):
            raise Http404("Dieses Objekt unterstützt keine Bilder.")
        queryset = model.objects
        if hasattr(queryset, "restrict"):
            queryset = queryset.restrict(request.user, "view")
        return get_object_or_404(queryset, pk=object_id)

    @staticmethod
    def _image_error_reason(image):
        """Return the underlying Pillow error, which Django hides behind a generic message."""
        from PIL import Image

        try:
            if hasattr(image, "temporary_file_path"):
                source = image.temporary_file_path()
            else:
                image.seek(0)
                source = BytesIO(image.read())
            with Image.open(source) as opened:
                opened.verify()
        except Exception as error:  # noqa: BLE001 - surface any Pillow failure
            return f"{type(error).__name__}: {error}"
        finally:
            if hasattr(image, "seek"):
                image.seek(0)
        return None

    @staticmethod
    def _build_image_forms(parent, cleaned_data):
        image_forms = []
        for image in cleaned_data["images"]:
            if hasattr(image, "seek"):
                image.seek(0)
            image_forms.append(
                ImageAttachmentForm(
                    data={"name": "", "description": cleaned_data["description"]},
                    files={"image": image},
                    instance=ImageAttachment(parent=parent),
                )
            )
        return image_forms

    def _return_url(self, request, parent):
        candidate = request.POST.get("return_url") or request.GET.get("return_url")
        if candidate and url_has_allowed_host_and_scheme(
            candidate,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return candidate
        return parent.get_absolute_url()

    def _render(self, request, form, parent):
        object_type = ContentType.objects.get_for_model(parent)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "parent": parent,
                "object_type": object_type.pk,
                "return_url": self._return_url(request, parent),
            },
        )


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
                request.POST.get("width"),
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


def _media_data_uri_loader():
    import base64
    import mimetypes
    from urllib.parse import urlparse

    from django.conf import settings
    from django.core.files.storage import default_storage

    media_url_path = urlparse(settings.MEDIA_URL).path

    def load(href):
        storage_path = urlparse(href).path
        if media_url_path and storage_path.startswith(media_url_path):
            storage_path = storage_path[len(media_url_path) :]
        storage_path = storage_path.lstrip("/")
        try:
            if not storage_path or not default_storage.exists(storage_path):
                return None
            with default_storage.open(storage_path, "rb") as image_file:
                data = image_file.read()
        except OSError:
            return None

        mime_type, _ = mimetypes.guess_type(storage_path)
        mime_type = mime_type or "application/octet-stream"
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    return load


class RackElevationOfflineSVGView(LoginRequiredMixin, View):
    """Serve a rack elevation SVG stripped of hyperlinks, for offline use."""

    def get(self, request, pk):
        if not offline_svg_export_enabled():
            return HttpResponseBadRequest("Der Offline-SVG-Export ist deaktiviert.")

        rack = get_object_or_404(Rack.objects.restrict(request.user, "view"), pk=pk)
        face = request.GET.get("face", "front")
        if face not in ("front", "rear"):
            return HttpResponseBadRequest("Ungültige Rack-Seite.")
        view_mode = request.GET.get("view", "images-and-labels")
        if view_mode not in RACK_VIEW_MODES:
            return HttpResponseBadRequest("Ungültige Ansicht.")

        from dcim.api.views import RackViewSet
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        api_request = factory.get(
            f"/api/dcim/racks/{rack.pk}/elevation/",
            {"render": "svg", "face": face},
        )
        api_request.user = request.user
        drf_view = RackViewSet.as_view({"get": "elevation"})
        response = drf_view(api_request, pk=rack.pk)
        if hasattr(response, "render"):
            response.render()

        svg_content = apply_rack_view_mode(response.content, view_mode)
        offline_svg = strip_svg_hyperlinks(svg_content, image_loader=_media_data_uri_loader())
        filename = f"{rack.name}-{face}-offline.svg".replace(" ", "_")
        http_response = HttpResponse(offline_svg, content_type="image/svg+xml")
        http_response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return http_response
