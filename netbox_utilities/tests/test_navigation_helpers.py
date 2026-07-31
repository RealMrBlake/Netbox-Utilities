from django.test import SimpleTestCase

from netbox_utilities.navigation_helpers import (
    SIDEBAR_WIDTH_DEFAULT,
    SIDEBAR_WIDTH_MAX,
    SIDEBAR_WIDTH_MIN,
    normalize_preferences,
    normalize_sidebar_width,
    update_sidebar_layout,
)


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


class SidebarLayoutTest(SimpleTestCase):
    def test_clamps_width_without_discrete_steps(self):
        self.assertEqual(normalize_sidebar_width(None), SIDEBAR_WIDTH_DEFAULT)
        self.assertEqual(normalize_sidebar_width(100), SIDEBAR_WIDTH_MIN)
        self.assertEqual(normalize_sidebar_width(500), SIDEBAR_WIDTH_MAX)
        self.assertEqual(normalize_sidebar_width(300), 300)

    def test_toggles_icon_only_mode(self):
        collapsed, width = update_sidebar_layout(False, SIDEBAR_WIDTH_DEFAULT, "toggle")

        self.assertTrue(collapsed)
        self.assertEqual(width, SIDEBAR_WIDTH_DEFAULT)

    def test_resizes_continuously_within_limits_and_expands(self):
        self.assertEqual(update_sidebar_layout(True, SIDEBAR_WIDTH_DEFAULT, "resize", 301), (False, 301))
        self.assertEqual(
            update_sidebar_layout(False, SIDEBAR_WIDTH_DEFAULT, "resize", 100),
            (False, SIDEBAR_WIDTH_MIN),
        )
        self.assertEqual(
            update_sidebar_layout(False, SIDEBAR_WIDTH_DEFAULT, "resize", 500),
            (False, SIDEBAR_WIDTH_MAX),
        )

    def test_rejects_unknown_action(self):
        with self.assertRaisesMessage(ValueError, "Unbekannte Navigationsaktion"):
            update_sidebar_layout(False, SIDEBAR_WIDTH_DEFAULT, "invalid")
