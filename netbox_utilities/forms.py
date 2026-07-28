from django import forms

from .models import UtilitiesSettings


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
