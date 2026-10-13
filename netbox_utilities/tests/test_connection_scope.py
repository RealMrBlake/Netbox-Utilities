from pathlib import Path

from django import forms
from django.test import SimpleTestCase

from netbox_utilities.connection_scope import (
    SITE_FIELD,
    TENANT_FIELD,
    TENANT_GROUP_FIELD,
    add_query_param,
    apply_connection_scope,
    build_filter_fields,
)
from netbox_utilities.tenant_scope import ActiveTenantScope, active_tenant_scope


class _Widget(forms.Select):
    def __init__(self):
        super().__init__()
        self.added = {}

    def add_query_param(self, name, value):
        self.added[name] = value


class _TerminationField(forms.Field):
    def __init__(self):
        super().__init__(required=False, widget=_Widget())
        self.query_params = {}


class _Form(forms.Form):
    def __init__(self, termination_fields=(), **kwargs):
        super().__init__(**kwargs)
        for name in termination_fields:
            self.fields[name] = _TerminationField()


class ConnectionScopeFieldTest(SimpleTestCase):
    # Pre-filling the tenant also looks up the tenant group (read-only query).
    databases = {"default"}

    def test_filter_fields_are_optional_and_chained(self):
        fields = build_filter_fields()

        self.assertEqual(set(fields), {TENANT_GROUP_FIELD, TENANT_FIELD, SITE_FIELD})
        for field in fields.values():
            self.assertFalse(field.required)
        self.assertEqual(fields[TENANT_FIELD].query_params, {"group_id": f"${TENANT_GROUP_FIELD}"})

    def test_add_query_param_updates_field_and_widget(self):
        field = _TerminationField()

        add_query_param(field, "tenant_id", f"${TENANT_FIELD}")

        self.assertEqual(field.query_params, {"tenant_id": f"${TENANT_FIELD}"})
        self.assertEqual(field.widget.added, {"tenant_id": f"${TENANT_FIELD}"})

    def test_device_selection_is_filtered_by_all_three_fields(self):
        form = _Form(termination_fields=("termination_b_device",))

        apply_connection_scope(form)

        self.assertEqual(
            form.fields["termination_b_device"].query_params,
            {
                "tenant_group_id": f"${TENANT_GROUP_FIELD}",
                "tenant_id": f"${TENANT_FIELD}",
                "site_id": f"${SITE_FIELD}",
            },
        )

    def test_power_panel_selection_is_filtered_by_site_only(self):
        form = _Form(termination_fields=("termination_b_powerpanel",))

        apply_connection_scope(form)

        self.assertEqual(form.fields["termination_b_powerpanel"].query_params, {"site_id": f"${SITE_FIELD}"})

    def test_a_side_fields_are_never_filtered(self):
        form = _Form(termination_fields=("termination_a_device", "termination_b_device"))

        apply_connection_scope(form)

        self.assertEqual(form.fields["termination_a_device"].query_params, {})

    def test_global_tenant_filter_prefills_the_tenant_field(self):
        form = _Form()
        token = active_tenant_scope.set(ActiveTenantScope(kind="tenant", object_id=7, tenant_ids=frozenset({7})))
        try:
            apply_connection_scope(form)
        finally:
            active_tenant_scope.reset(token)

        self.assertEqual(form.initial[TENANT_FIELD], 7)

    def test_global_group_filter_prefills_the_group_field(self):
        form = _Form()
        token = active_tenant_scope.set(ActiveTenantScope(kind="group", object_id=3, tenant_ids=frozenset({7, 8})))
        try:
            apply_connection_scope(form)
        finally:
            active_tenant_scope.reset(token)

        self.assertEqual(form.initial[TENANT_GROUP_FIELD], 3)
        self.assertNotIn(TENANT_FIELD, form.initial)

    def test_bound_forms_keep_the_submitted_filter_values(self):
        form = _Form(data={TENANT_FIELD: ""})
        token = active_tenant_scope.set(ActiveTenantScope(kind="tenant", object_id=7, tenant_ids=frozenset({7})))
        try:
            apply_connection_scope(form)
        finally:
            active_tenant_scope.reset(token)

        self.assertEqual(form.initial, {})


class ConnectionScopeTemplateTest(SimpleTestCase):
    def test_filter_fields_are_rendered_above_the_b_side_device(self):
        template_path = Path(__file__).parents[1] / "templates" / "netbox_utilities" / "cable_edit_form.html"
        template = template_path.read_text(encoding="utf-8")

        b_side = template.index('{% trans "B Side" %}')
        group_filter = template.index(f"{{% render_field form.{TENANT_GROUP_FIELD} %}}")
        tenant_filter = template.index(f"{{% render_field form.{TENANT_FIELD} %}}")
        site_filter = template.index(f"{{% render_field form.{SITE_FIELD} %}}")
        device_field = template.index("{% render_field form.termination_b_device %}")

        self.assertLess(b_side, group_filter)
        self.assertLess(group_filter, tenant_filter)
        self.assertLess(tenant_filter, site_filter)
        self.assertLess(site_filter, device_field)
        self.assertNotIn(f"form.{TENANT_FIELD} %}}\n    {{% render_field form.termination_a_device", template)
