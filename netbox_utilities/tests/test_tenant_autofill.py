from types import SimpleNamespace
from unittest.mock import patch

from django import forms
from django.test import SimpleTestCase
from tenancy.models import TenantGroup

from netbox_utilities.tenant_autofill import apply_tenant_autofill, infer_tenant_id, tenant_id_from_object
from netbox_utilities.tenant_scope import ActiveTenantScope, active_tenant_scope


class FakeMeta:
    def __init__(self, *field_names):
        self.field_names = field_names

    def get_fields(self):
        return [SimpleNamespace(name=name) for name in self.field_names]


class FakeObject:
    def __init__(self, *, tenant_id=None, **relations):
        self.tenant_id = tenant_id
        self._meta = FakeMeta("tenant", *relations)
        for name, value in relations.items():
            setattr(self, name, value)


class FakeQuerySet:
    def __init__(self, model):
        self.model = model


class TenantAutofillTest(SimpleTestCase):
    def test_finds_tenant_through_parent_relation(self):
        rack = FakeObject(tenant_id=42)
        device = FakeObject(rack=rack)

        self.assertEqual(tenant_id_from_object(device), 42)

    def test_uses_selected_global_tenant_as_fallback(self):
        form = SimpleNamespace(
            fields={"tenant": forms.IntegerField()},
            initial={},
            instance=FakeObject(),
            is_bound=False,
        )
        token = active_tenant_scope.set(ActiveTenantScope("tenant", 17, frozenset({17})))
        try:
            self.assertEqual(infer_tenant_id(form), 17)
        finally:
            active_tenant_scope.reset(token)

    @patch("netbox_utilities.tenant_autofill._infer_group_id", return_value=None)
    @patch("netbox_utilities.tenant_autofill.infer_tenant_id", return_value=23)
    def test_prefills_and_marks_tenant_field(self, _infer_tenant_id, _infer_group_id):
        tenant_field = forms.IntegerField()
        form = SimpleNamespace(
            fields={"tenant": tenant_field},
            initial={},
            instance=FakeObject(),
            is_bound=False,
        )

        apply_tenant_autofill(form)

        self.assertEqual(form.initial["tenant"], 23)
        self.assertEqual(tenant_field.widget.attrs["data-netbox-utilities-autofilled-tenant"], "23")

    @patch("netbox_utilities.tenant_autofill._infer_group_id", return_value=9)
    def test_prefills_tenant_group_relation(self, _infer_group_id):
        group_field = SimpleNamespace(
            queryset=FakeQuerySet(TenantGroup),
            help_text="",
        )
        form = SimpleNamespace(
            fields={"group": group_field},
            initial={},
            instance=SimpleNamespace(group_id=None),
            is_bound=False,
        )

        apply_tenant_autofill(form)

        self.assertEqual(form.initial["group"], 9)
