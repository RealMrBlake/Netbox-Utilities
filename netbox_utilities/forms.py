from dcim.choices import ModuleStatusChoices
from dcim.models import Device, ModuleBay, ModuleType
from django import forms
from extras.constants import IMAGE_ATTACHMENT_IMAGE_FORMATS
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField

from .models import UtilitiesSettings


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if not data:
            return super().clean(data, initial)
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super().clean(file, initial) for file in files]


class BulkImageUploadForm(forms.Form):
    images = MultipleImageField(
        label="Bilder",
        widget=MultipleImageInput(
            attrs={
                "accept": ",".join(sorted(set(IMAGE_ATTACHMENT_IMAGE_FORMATS.values()))),
                "class": "netbox-utilities-multi-image-input",
            }
        ),
        help_text="Bis zu 50 Bilder auswählen. Alle Dateien werden demselben NetBox-Objekt zugeordnet.",
    )
    description = forms.CharField(
        label="Gemeinsame Beschreibung",
        required=False,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Optional: Diese Beschreibung wird für jedes ausgewählte Bild übernommen.",
    )

    def clean_images(self):
        images = self.cleaned_data["images"]
        if len(images) > 50:
            raise forms.ValidationError("Pro Upload können höchstens 50 Bilder verarbeitet werden.")
        return images


class BulkModuleInstallForm(forms.Form):
    device = DynamicModelChoiceField(
        label="Gerät",
        queryset=Device.objects.all(),
        selector=True,
    )
    module_type = DynamicModelChoiceField(
        label="Modultyp",
        queryset=ModuleType.objects.all(),
        context={"parent": "manufacturer"},
        selector=True,
    )
    module_bays = DynamicModelMultipleChoiceField(
        label="Modulschächte",
        queryset=ModuleBay.objects.all(),
        required=False,
        query_params={"device_id": "$device"},
        context={"disabled": "_occupied"},
        help_text="Bestimmte freie Schächte auswählen. Alternativ kann die Anzahl verwendet werden.",
    )
    quantity = forms.IntegerField(
        label="Anzahl (1–x)",
        required=False,
        min_value=1,
        help_text=(
            "Baut die angegebene Anzahl automatisch in die ersten freien Modulschächte ein. "
            "Nicht zusammen mit einer manuellen Schachtauswahl verwenden."
        ),
    )
    status = forms.ChoiceField(
        label="Status",
        choices=ModuleStatusChoices,
        initial=ModuleStatusChoices.STATUS_ACTIVE,
    )
    replicate_components = forms.BooleanField(
        label="Komponenten replizieren",
        required=False,
        initial=True,
        help_text="Komponenten aus den Vorlagen des Modultyps automatisch anlegen.",
    )
    description = forms.CharField(
        label="Beschreibung",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["device"].queryset = Device.objects.restrict(user, "view")
        self.fields["module_type"].queryset = ModuleType.objects.restrict(user, "view")

        module_bays = ModuleBay.objects.restrict(user, "view").filter(
            enabled=True,
            installed_module__isnull=True,
        )
        device = self.data.get("device") or self.initial.get("device")
        if isinstance(device, Device):
            device = device.pk
        if device:
            module_bays = module_bays.filter(device_id=device)
        self.available_module_bays = module_bays
        self.fields["module_bays"].queryset = module_bays

    def clean(self):
        cleaned_data = super().clean()
        device = cleaned_data.get("device")
        module_bays = cleaned_data.get("module_bays")
        quantity = cleaned_data.get("quantity")

        if module_bays and quantity:
            self.add_error("quantity", "Anzahl und manuelle Schachtauswahl können nicht kombiniert werden.")
        elif not module_bays and not quantity and "module_bays" not in self.errors and "quantity" not in self.errors:
            self.add_error(None, "Wählen Sie Modulschächte aus oder geben Sie eine Anzahl ein.")
        elif quantity and device:
            available_bays = self.available_module_bays
            available_count = available_bays.count()
            if quantity > available_count:
                availability = (
                    "nur ein freier Modulschacht"
                    if available_count == 1
                    else f"nur {available_count} freie Modulschächte"
                )
                self.add_error(
                    "quantity",
                    f"Für dieses Gerät sind {availability} verfügbar.",
                )
            else:
                cleaned_data["module_bays"] = list(available_bays[:quantity])

        if device and module_bays:
            invalid_bays = [
                module_bay.name
                for module_bay in module_bays
                if module_bay.device_id != device.pk
                or not module_bay.enabled
                or hasattr(module_bay, "installed_module")
            ]
            if invalid_bays:
                self.add_error(
                    "module_bays",
                    "Diese Modulschächte sind nicht frei oder gehören nicht zum gewählten Gerät: "
                    + ", ".join(invalid_bays),
                )
        return cleaned_data


class UtilitiesSettingsForm(forms.ModelForm):
    def __init__(self, *args, tenant_filter_locked=False, tenant_required_locked=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tenant_filter_enabled"].disabled = tenant_filter_locked
        self.fields["tenant_required"].disabled = tenant_required_locked

    class Meta:
        model = UtilitiesSettings
        fields = ("tenant_filter_enabled", "tenant_required")
        labels = {
            "tenant_filter_enabled": "Globalen Mandantenfilter aktivieren",
            "tenant_required": "Mandant für mandantenfähige Objekte verpflichtend machen",
        }
        help_texts = {
            "tenant_filter_enabled": (
                "Blendet das Mandanten-Dropdown ein und ergänzt unterstützte NetBox-Listen "
                "automatisch um den gewählten Mandantenfilter."
            ),
            "tenant_required": (
                "Verhindert das Speichern mandantenfähiger Objekte ohne Mandant. "
                "Dies gilt auch für Importe, API-Aufrufe und Skripte."
            ),
        }
        widgets = {
            "tenant_filter_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "tenant_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
