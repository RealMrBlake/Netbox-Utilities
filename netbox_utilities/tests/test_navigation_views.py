import json
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from netbox_utilities.views import NavigationLayoutView


class NavigationLayoutViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("netbox_utilities.views.navigation_customization_enabled", return_value=True)
    @patch("netbox_utilities.views.NavigationPreference.objects.get_or_create")
    def test_toggles_and_persists_icon_mode(self, get_or_create, _feature_enabled):
        preference = MagicMock(sidebar_collapsed=False, sidebar_width=288)
        get_or_create.return_value = (preference, False)
        request = self.factory.post("/plugins/utilities/navigation/layout/", {"action": "toggle"})
        request.user = MagicMock()

        response = NavigationLayoutView().post(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"collapsed": True, "width": 288})
        self.assertTrue(preference.sidebar_collapsed)
        preference.save.assert_called_once_with(update_fields=("sidebar_collapsed", "sidebar_width", "updated"))

    @patch("netbox_utilities.views.navigation_customization_enabled", return_value=True)
    @patch("netbox_utilities.views.NavigationPreference.objects.get_or_create")
    def test_saves_continuously_resized_width(self, get_or_create, _feature_enabled):
        preference = MagicMock(sidebar_collapsed=True, sidebar_width=288)
        get_or_create.return_value = (preference, False)
        request = self.factory.post(
            "/plugins/utilities/navigation/layout/",
            {"action": "resize", "width": "317"},
        )
        request.user = MagicMock()

        response = NavigationLayoutView().post(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"collapsed": False, "width": 317})
        self.assertFalse(preference.sidebar_collapsed)
        self.assertEqual(preference.sidebar_width, 317)

    @patch("netbox_utilities.views.navigation_customization_enabled", return_value=True)
    @patch("netbox_utilities.views.NavigationPreference.objects.get_or_create")
    def test_rejects_unknown_layout_action(self, get_or_create, _feature_enabled):
        get_or_create.return_value = (MagicMock(sidebar_collapsed=False, sidebar_width=288), False)
        request = self.factory.post("/plugins/utilities/navigation/layout/", {"action": "unknown"})
        request.user = MagicMock()

        response = NavigationLayoutView().post(request)

        self.assertEqual(response.status_code, 400)
