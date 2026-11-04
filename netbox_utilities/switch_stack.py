from django import forms
from django.core.exceptions import ValidationError

from .models import SwitchStack

STACK_FORM_FIELDS = ("utilities_switch_stack", "utilities_stack_members")


def stack_members(device):
    """Member devices of the stack represented by the device, in natural name order; [] if it is no stack."""
    from .switch_ports import natural_key

    if device is None or not device.pk:
        return []
    stack = SwitchStack.objects.filter(device=device).first()
    if stack is None:
        return []
    members = stack.members.exclude(pk=device.pk).select_related("role", "site", "rack", "device_type")
    return sorted(members, key=lambda member: natural_key(member.name or str(member)))


def build_stack_form_mixin():
    from dcim.models import Device
    from utilities.forms.fields import DynamicModelMultipleChoiceField

    class SwitchStackFormMixin(forms.Form):
        utilities_switch_stack = forms.BooleanField(
            label="Switch-Stack",
            required=False,
            help_text="Dieser Switch steht für einen Stack; die Mitglieder werden in der Ports-Übersicht "
            "untereinander abgebildet.",
        )
        utilities_stack_members = DynamicModelMultipleChoiceField(
            label="Stack-Mitglieder",
            queryset=Device.objects.all(),
            required=False,
            query_params={"role_id": "$role"},
            help_text="Weitere Switches des Stacks (dieser Switch ist immer das erste Mitglied).",
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not self.is_bound and self.instance.pk:
                members = stack_members(self.instance)
                self.initial["utilities_switch_stack"] = SwitchStack.objects.filter(device=self.instance).exists()
                self.initial["utilities_stack_members"] = [member.pk for member in members]

        def clean(self):
            super().clean()
            members = list(self.cleaned_data.get("utilities_stack_members") or [])
            if self.instance.pk and any(member.pk == self.instance.pk for member in members):
                self.add_error("utilities_stack_members", ValidationError("Der Switch kann nicht sein eigenes Mitglied sein."))
            return self.cleaned_data

        def save(self, commit=True):
            device = super().save(commit=commit)
            if commit:
                save_stack(device, self.cleaned_data.get("utilities_switch_stack"), self.cleaned_data.get("utilities_stack_members"))
            return device

    return SwitchStackFormMixin


def save_stack(device, is_stack, members):
    if not is_stack:
        SwitchStack.objects.filter(device=device).delete()
        return
    stack, _ = SwitchStack.objects.get_or_create(device=device)
    stack.members.set([member for member in members or [] if member.pk != device.pk])
