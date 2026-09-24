from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities.site_prefix import COLUMN_NAME, SitePrefixColumn, first_word, prepend_to_default_columns


class SitePrefixTest(SimpleTestCase):
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
        self.assertEqual(DeviceTable.Meta.default_columns[:2], ("pk", COLUMN_NAME))
        self.assertEqual(RackTable.Meta.default_columns[:2], ("pk", COLUMN_NAME))
