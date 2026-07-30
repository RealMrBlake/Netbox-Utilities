from dcim.choices import ModuleStatusChoices
from dcim.models import Device, ModuleBay, ModuleType
from django import forms
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField

from .models import UtilitiesSettings


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
        query_params={"device_id": "$device"},
        context={"disabled": "_occupied"},
        help_text="Alle ausgewählten Modulschächte erhalten ein Modul des gewählten Typs.",
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
        self.fields["module_bays"].queryset = module_bays

    def clean(self):
        cleaned_data = super().clean()
        device = cleaned_data.get("device")
        module_bays = cleaned_data.get("module_bays")
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
