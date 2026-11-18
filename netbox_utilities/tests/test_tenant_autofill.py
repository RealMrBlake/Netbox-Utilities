from types import SimpleNamespace
from unittest.mock import patch

from django import forms
from django.test import SimpleTestCase
from tenancy.models import TenantGroup

from netbox_utilities.tenant_autofill import (
    apply_asset_instance_tenant,
    apply_cable_instance_tenant,
    apply_tenant_autofill,
    infer_tenant_id,
    tenant_id_from_cable_terminations,
    tenant_id_from_object,
)
from netbox_utilities.tenant_scope import ActiveTenantScope, active_tenant_scope


class FakeMeta:
    def __init__(self, *field_names):
        self.field_names = field_names

    def get_fields(self):
        return [SimpleNamespace(name=name) for name in self.field_names]


class FakeCableMeta(FakeMeta):
    app_label = "dcim"
    model_name = "cable"


class FakeObject:
    def __init__(self, *, tenant_id=None, **relations):
        self.tenant_id = tenant_id
        self._meta = FakeMeta("tenant", *relations)
        for name, value in relations.items():
            setattr(self, name, value)


class FakeCable(FakeObject):
    def __init__(self, *, tenant_id=None, a_terminations=None, b_terminations=None):
        super().__init__(tenant_id=tenant_id)
        self._meta = FakeCableMeta("tenant")
        self.a_terminations = a_terminations or []
        self.b_terminations = b_terminations or []


class FakeAssetMeta(FakeMeta):
    app_label = "netbox_inventory"
    model_name = "asset"


class FakeAsset(FakeObject):
    """netbox-inventory asset: tenant plus one of device, module, inventoryitem or rack."""

    def __init__(self, *, tenant_id=None, device=None, module=None, inventoryitem=None, rack=None):
        super().__init__(tenant_id=tenant_id)
        self._meta = FakeAssetMeta("tenant", "device", "module", "inventoryitem", "rack")
        self.device, self.module, self.inventoryitem, self.rack = device, module, inventoryitem, rack


class FakeQuerySet:
    def __init__(self, model):
        self.model = model


class TenantAutofillTest(SimpleTestCase):
    def test_netbox_vlan_group_reverse_scopes_do_not_break_autofill(self):
        from ipam.models import VLANGroup

        self.assertIsNone(tenant_id_from_object(VLANGroup()))

    def test_ignores_reverse_relation_managers_on_scoped_objects(self):
        reverse_manager = SimpleNamespace()
        vlan_group = FakeObject(site=reverse_manager, rack=reverse_manager)

        self.assertIsNone(tenant_id_from_object(vlan_group))

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

    def test_finds_common_cable_tenant_from_both_ends(self):
        terminations = [FakeObject(device=FakeObject(tenant_id=42)), FakeObject(device=FakeObject(tenant_id=42))]

        self.assertEqual(tenant_id_from_cable_terminations(terminations), 42)

    def test_does_not_guess_when_cable_ends_have_different_tenants(self):
        terminations = [FakeObject(device=FakeObject(tenant_id=42)), FakeObject(device=FakeObject(tenant_id=43))]

        self.assertIsNone(tenant_id_from_cable_terminations(terminations))

    def test_assigns_common_tenant_to_cable_instance(self):
        cable = FakeCable(
            a_terminations=[FakeObject(device=FakeObject(tenant_id=42))],
            b_terminations=[FakeObject(device=FakeObject(tenant_id=42))],
        )

        self.assertEqual(apply_cable_instance_tenant(cable), 42)
        self.assertEqual(cable.tenant_id, 42)

    def test_asset_takes_tenant_of_assigned_device(self):
        asset = FakeAsset(device=FakeObject(tenant_id=42))

        self.assertEqual(apply_asset_instance_tenant(asset), 42)
        self.assertEqual(asset.tenant_id, 42)

    def test_asset_takes_tenant_of_module_device_inventory_item_and_rack(self):
        device = FakeObject(tenant_id=7)
        for asset in (
            FakeAsset(module=FakeObject(device=device)),
            FakeAsset(inventoryitem=FakeObject(device=device)),
            FakeAsset(rack=FakeObject(tenant_id=7)),
        ):
            self.assertEqual(apply_asset_instance_tenant(asset), 7)

    def test_asset_keeps_existing_tenant_and_stays_empty_without_hardware(self):
        asset = FakeAsset(tenant_id=5, device=FakeObject(tenant_id=42))
        self.assertIsNone(apply_asset_instance_tenant(asset))
        self.assertEqual(asset.tenant_id, 5)

        stored = FakeAsset()
        self.assertIsNone(apply_asset_instance_tenant(stored))
        self.assertIsNone(stored.tenant_id)

    def test_other_models_are_not_assigned_a_tenant_from_their_device(self):
        interface_like = FakeObject(device=FakeObject(tenant_id=42))

        self.assertIsNone(apply_asset_instance_tenant(interface_like))
        self.assertIsNone(interface_like.tenant_id)

    def test_prefers_cable_terminations_over_global_scope(self):
        form = SimpleNamespace(
            fields={"tenant": forms.IntegerField()},
            initial={},
            instance=FakeCable(a_terminations=[FakeObject(device=FakeObject(tenant_id=42))]),
            is_bound=False,
        )
        token = active_tenant_scope.set(ActiveTenantScope("tenant", 17, frozenset({17})))
        try:
            self.assertEqual(infer_tenant_id(form), 42)
        finally:
            active_tenant_scope.reset(token)

    def test_conflicting_cable_ends_do_not_fall_back_to_global_scope(self):
        form = SimpleNamespace(
            fields={"tenant": forms.IntegerField()},
            initial={},
            instance=FakeCable(
                a_terminations=[FakeObject(device=FakeObject(tenant_id=42))],
                b_terminations=[FakeObject(device=FakeObject(tenant_id=43))],
            ),
            is_bound=False,
        )
        token = active_tenant_scope.set(ActiveTenantScope("tenant", 17, frozenset({17})))
        try:
            self.assertIsNone(infer_tenant_id(form))
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
