from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.context_processors import PermWrapper
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from netbox_utilities.template_content import UtilitiesGlobalContent


class OptionalRackIntegrationHeadTest(SimpleTestCase):
    @staticmethod
    def _context(path):
        request = RequestFactory().get(path)
        request.user = AnonymousUser()
        return {
            "request": request,
            "settings": settings,
            "csrf_token": "",
            "perms": PermWrapper(request.user),
        }

    def test_reorder_adapter_is_emitted_for_an_empty_enabled_payload(self):
        data = {
            "columns": 12,
            "unit_width": 220,
            "images": True,
            "labels": True,
            "devices": [],
            "status": "ready",
            "schema_version": 3,
            "complete": True,
        }
        with (
            patch("netbox_utilities.template_content.get_reorder_rack_width_data", return_value=data),
            patch("netbox_utilities.template_content.get_topology_rack_width_data", return_value=None),
        ):
            html = UtilitiesGlobalContent(self._context("/dcim/racks/3/reorder/")).head()

        self.assertIn('id="netbox-utilities-reorder-rack-width-data"', html)
        self.assertIn("netbox_utilities/reorder-rack-width.js", html)
        self.assertIn('"status": "ready"', html)

    def test_topology_adapter_is_emitted_for_an_empty_enabled_payload(self):
        data = {"devices": [], "status": "ready", "schema_version": 3, "complete": True}
        with (
            patch("netbox_utilities.template_content.get_reorder_rack_width_data", return_value=None),
            patch("netbox_utilities.template_content.get_topology_rack_width_data", return_value=data),
        ):
            html = UtilitiesGlobalContent(
                self._context("/plugins/netbox_topology_views/rack-elevation/?rack_id=3")
            ).head()

        self.assertIn('id="netbox-utilities-topology-rack-width-data"', html)
        self.assertIn("netbox_utilities/topology-rack-width.js", html)
        self.assertIn('"status": "ready"', html)

    def test_topology_widths_are_rendered_server_side_without_javascript(self):
        data = {
            "devices": [
                {
                    "device_id": 17,
                    "url": "/dcim/devices/17/",
                    "left_percent": 50,
                    "width_percent": 50,
                }
            ],
            "status": "ready",
            "schema_version": 3,
            "complete": True,
        }
        with (
            patch("netbox_utilities.template_content.get_reorder_rack_width_data", return_value=None),
            patch("netbox_utilities.template_content.get_topology_rack_width_data", return_value=data),
        ):
            html = UtilitiesGlobalContent(
                self._context("/plugins/netbox_topology_views/rack-elevation/?rack_id=3")
            ).head()

        self.assertIn('id="netbox-utilities-topology-rack-width-styles"', html)
        self.assertIn('.rack-device[href="/dcim/devices/17/"]', html)
        self.assertIn("left: calc(50% + 3px) !important", html)
        self.assertIn("width: calc(50% - 6px) !important", html)
