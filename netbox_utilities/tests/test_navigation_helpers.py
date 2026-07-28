from django.test import SimpleTestCase

from netbox_utilities.navigation_helpers import normalize_preferences


class NormalizePreferencesTest(SimpleTestCase):
    def test_removes_unknown_and_duplicate_keys(self):
        order, hidden = normalize_preferences(
            ["devices", "unknown", "devices"],
            ["ipam", "unknown", "ipam"],
            ["organization", "devices", "ipam"],
        )

        self.assertEqual(order, ["devices", "organization", "ipam"])
        self.assertEqual(hidden, ["ipam"])

    def test_new_menus_are_appended(self):
        order, hidden = normalize_preferences(["devices"], [], ["devices", "vpn"])

        self.assertEqual(order, ["devices", "vpn"])
        self.assertEqual(hidden, [])
