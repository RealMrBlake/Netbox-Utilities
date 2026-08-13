from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from netbox_utilities.topology_views import (
    get_topology_rack_width_data,
    is_topology_rack_elevation_request,
    serialize_topology_placement,
    topology_rack_width_enabled,
)


class TopologyViewsRackWidthTest(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/plugins/netbox_topology_views/rack-elevation/?rack_id=3")
        self.request.user = MagicMock()

    def test_detects_only_topology_rack_elevation_route(self):
        self.request.resolver_match = SimpleNamespace(view_name="plugins:netbox_topology_views:rack_elevation")
        self.assertTrue(is_topology_rack_elevation_request(self.request))

        self.request.resolver_match = SimpleNamespace(view_name="dcim:rack_list")
        self.assertFalse(is_topology_rack_elevation_request(self.request))

    def test_skips_integration_when_optional_plugin_is_missing(self):
        self.request.resolver_match = SimpleNamespace(view_name="plugins:netbox_topology_views:rack_elevation")
        with (
            patch("netbox_utilities.topology_views.apps.is_installed", return_value=False),
            patch("netbox_utilities.topology_views.get_plugin_config", return_value=True),
        ):
            self.assertFalse(topology_rack_width_enabled(self.request))

    def test_skips_integration_when_admin_disabled_it(self):
        self.request.resolver_match = SimpleNamespace(view_name="plugins:netbox_topology_views:rack_elevation")
        with (
            patch("netbox_utilities.topology_views.apps.is_installed", return_value=True),
            patch("netbox_utilities.topology_views.get_plugin_config", return_value=False),
        ):
            self.assertFalse(topology_rack_width_enabled(self.request))

    def test_serializes_fractional_width_geometry_and_device_url(self):
        placement = SimpleNamespace(
            device_id=17,
            device=SimpleNamespace(get_absolute_url=lambda: "/dcim/devices/17/"),
            width=3,
            horizontal_position=2,
        )

        self.assertEqual(
            serialize_topology_placement(placement),
            {
                "device_id": 17,
                "url": "/dcim/devices/17/",
                "width": 3,
                "horizontal_position": 2,
                "left_percent": 33.33333333,
                "width_percent": 33.33333333,
            },
        )

    @patch("netbox_utilities.topology_views.DeviceRackPlacement.objects")
    @patch("netbox_utilities.topology_views.topology_rack_width_enabled", return_value=True)
    def test_queries_only_permitted_devices_from_selected_racks(self, _enabled, placement_objects):
        self.request.resolver_match = SimpleNamespace(view_name="plugins:netbox_topology_views:rack_elevation")
        rack_queryset = MagicMock()
        rack_queryset.filter.return_value = rack_queryset
        rack_queryset.values.return_value = "selected-rack-query"
        rack_model = MagicMock()
        rack_model.objects.restrict.return_value = rack_queryset

        device_queryset = MagicMock()
        device_queryset.filter.return_value = "permitted-device-query"
        device_model = MagicMock()
        device_model.objects.restrict.return_value = device_queryset

        placement = SimpleNamespace(
            device_id=17,
            device=SimpleNamespace(get_absolute_url=lambda: "/dcim/devices/17/"),
            width=2,
            horizontal_position=2,
        )
        placement_queryset = MagicMock()
        placement_queryset.select_related.return_value.order_by.return_value = [placement]
        placement_objects.filter.return_value = placement_queryset

        with patch.dict("sys.modules", {"dcim.models": SimpleNamespace(Device=device_model, Rack=rack_model)}):
            result = get_topology_rack_width_data(self.request)

        rack_queryset.filter.assert_called_once_with(pk__in=["3"])
        device_queryset.filter.assert_called_once_with(
            rack_id__in="selected-rack-query",
            position__isnull=False,
        )
        placement_objects.filter.assert_called_once_with(device__in="permitted-device-query")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["devices"][0]["width"], 2)
        self.assertEqual(result["devices"][0]["horizontal_position"], 2)

    def test_frontend_supports_live_view_and_all_rack_export_formats(self):
        script = (Path(__file__).parents[1] / "static" / "netbox_utilities" / "topology-rack-width.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("netbox-utilities-partial-width", script)
        self.assertIn("horizontalGeometry", script)
        self.assertIn("buildRackSvg", script)
        self.assertIn("buildRackDrawio", script)
        self.assertIn("format === 'svg'", script)
        self.assertIn("format === 'drawio'", script)
        self.assertIn("canvas.toBlob", script)
        self.assertIn("event.stopImmediatePropagation()", script)
        self.assertIn("rackExportCompatible", script)
        self.assertIn("liveViewCompatible", script)
        self.assertIn("payload?.devices", script)
        self.assertIn("payload.status !== 'ready'", script)
        self.assertLess(script.index("liveViewCompatible"), script.index("netbox-utilities-partial-width"))
        self.assertLess(script.index("exportGraphic(graphic"), script.index("event.preventDefault()"))

    @patch("netbox_utilities.topology_views.topology_rack_width_enabled", return_value=True)
    def test_malformed_partial_placement_fails_open(self, _enabled):
        self.request.resolver_match = SimpleNamespace(view_name="plugins:netbox_topology_views:rack_elevation")
        with patch("dcim.models.Rack.objects.restrict", side_effect=AttributeError("stale")):
            result = get_topology_rack_width_data(self.request)

        self.assertEqual(result["status"], "native-fallback")
        self.assertEqual(result["devices"], [])

    def test_partial_width_css_uses_topology_device_slot_geometry(self):
        stylesheet = (Path(__file__).parents[1] / "static" / "netbox_utilities" / "netbox_utilities.css").read_text(
            encoding="utf-8"
        )

        self.assertIn(".rack-device.netbox-utilities-partial-width", stylesheet)
        self.assertIn("--netbox-utilities-rack-device-left", stylesheet)
        self.assertIn("--netbox-utilities-rack-device-width", stylesheet)
