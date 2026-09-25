from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities.site_prefix import (
    COLUMN_NAME,
    SitePrefixColumn,
    first_word,
    insert_into_fieldsets,
    prepend_to_default_columns,
    site_prefix_query,
    split_prefixes,
)


class SitePrefixTest(SimpleTestCase):
    def test_split_prefixes_accepts_commas_and_repeated_values(self):
        self.assertEqual(split_prefixes(["Berlin, DC01", "HH", "DC01", " "]), ["Berlin", "DC01", "HH"])
        self.assertEqual(split_prefixes(None), [])

    def test_prefix_query_matches_only_the_whole_first_word(self):
        query = str(site_prefix_query(["DC01"]))

        self.assertIn("('site__name__iexact', 'DC01')", query)
        self.assertIn("('site__name__iregex', '^DC01\\\\s')", query)

    def test_prefix_query_escapes_regex_characters(self):
        self.assertIn("^DC\\\\.1\\\\s", str(site_prefix_query(["DC.1"])))

    def test_prefix_field_is_placed_after_site_filter(self):
        from utilities.forms.rendering import FieldSet

        fieldsets = insert_into_fieldsets(
            (FieldSet("q", name="Suche"), FieldSet("region_id", "site_id", "location_id", name="Standort")),
            COLUMN_NAME,
        )

        self.assertEqual(fieldsets[1].items, ("region_id", "site_id", COLUMN_NAME, "location_id"))
        self.assertEqual(fieldsets[1].name, "Standort")

    def test_device_and_rack_filters_offer_prefix(self):
        from dcim.filtersets import DeviceFilterSet, RackFilterSet
        from dcim.forms import DeviceFilterForm, RackFilterForm

        for filterset in (DeviceFilterSet, RackFilterSet):
            self.assertIn(COLUMN_NAME, filterset.base_filters)
        for form in (DeviceFilterForm, RackFilterForm):
            self.assertIn(COLUMN_NAME, form.base_fields)
            self.assertTrue(any(COLUMN_NAME in fieldset.items for fieldset in form.fieldsets))

    def test_first_word(self):
        self.assertEqual(first_word("Berlin Campus West"), "Berlin")
        self.assertEqual(first_word("  DC01\tFrankfurt "), "DC01")

    def test_first_word_handles_missing_or_blank_value(self):
        self.assertIsNone(first_word(None))
        self.assertIsNone(first_word("   "))

    def test_column_renders_first_word_of_site_name(self):
        column = SitePrefixColumn()

        self.assertEqual(column.render(SimpleNamespace(name="DC01 Frankfurt")), "DC01")
        self.assertIsNone(column.render(None))

    def test_prefix_column_is_first_default_column(self):
        table = SimpleNamespace(Meta=SimpleNamespace(default_columns=("pk", "name", COLUMN_NAME, "status")))

        prepend_to_default_columns(table)

        self.assertEqual(table.Meta.default_columns, ("pk", COLUMN_NAME, "name", "status"))

    def test_device_and_rack_tables_offer_prefix_column(self):
        from dcim.tables import DeviceTable, RackTable

        self.assertIn(COLUMN_NAME, DeviceTable.base_columns)
        self.assertIn(COLUMN_NAME, RackTable.base_columns)
        for table in (DeviceTable, RackTable):
            column = table.base_columns[COLUMN_NAME]
            self.assertTrue(column.orderable)
            self.assertEqual(tuple(column.order_by), ("site__name",))
        self.assertEqual(DeviceTable.Meta.default_columns[:2], ("pk", COLUMN_NAME))
        self.assertEqual(RackTable.Meta.default_columns[:2], ("pk", COLUMN_NAME))
