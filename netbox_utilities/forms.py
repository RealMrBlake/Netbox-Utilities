from django import forms

from .models import UtilitiesSettings


class UtilitiesSettingsForm(forms.ModelForm):
    class Meta:
        model = UtilitiesSettings
        fields = ("tenant_filter_enabled",)
        labels = {
            "tenant_filter_enabled": "Globalen Mandantenfilter aktivieren",
        }
        help_texts = {
            "tenant_filter_enabled": (
                "Blendet das Mandanten-Dropdown ein und ergänzt unterstützte NetBox-Listen "
                "automatisch um den gewählten Mandantenfilter."
            ),
        }
        widgets = {
            "tenant_filter_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
