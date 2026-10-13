from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

import netbox_utilities
from netbox_utilities.topology_views import (
    _apply_topology_widths_to_device_tags,
    _inject_topology_widths,
    _topology_data_for_visible_devices,
    _visible_topology_device_urls,
    apply_topology_rack_widths,
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
            device=SimpleNamespace(pk=17, get_absolute_url=lambda: "/dcim/devices/17/"),
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
                "width_source": "stored",
            },
        )

    @patch("netbox_utilities.topology_views.topology_rack_width_enabled", return_value=True)
    def test_queries_all_permitted_devices_and_infers_shared_unit_widths(self, _enabled):
        self.request.resolver_match = SimpleNamespace(view_name="plugins:netbox_topology_views:rack_elevation")
        rack_queryset = MagicMock()
        rack_queryset.filter.return_value = rack_queryset
        rack_queryset.values.return_value = "selected-rack-query"
        rack_model = MagicMock()
        rack_model.objects.restrict.return_value = rack_queryset

        device_queryset = MagicMock()
        selected_devices = MagicMock()
        device_queryset.filter.return_value = selected_devices
        device_model = MagicMock()
        device_model.objects.restrict.return_value = device_queryset

        devices = [
            SimpleNamespace(
                pk=17,
                rack_id=3,
                face="front",
                position=11,
                device_type=SimpleNamespace(u_height=1),
                netbox_utilities_rack_placement=None,
                get_absolute_url=lambda: "/dcim/devices/17/",
            ),
            SimpleNamespace(
                pk=18,
                rack_id=3,
                face="front",
                position=11,
                device_type=SimpleNamespace(u_height=1),
                netbox_utilities_rack_placement=None,
                get_absolute_url=lambda: "/dcim/devices/18/",
            ),
        ]
        selected_devices.select_related.return_value.order_by.return_value = devices

        with patch.dict("sys.modules", {"dcim.models": SimpleNamespace(Device=device_model, Rack=rack_model)}):
            result = get_topology_rack_width_data(self.request)

        rack_queryset.filter.assert_called_once_with(pk__in=["3"])
        device_queryset.filter.assert_called_once_with(
            rack_id__in="selected-rack-query",
            position__gt=0,
            device_type__u_height__gt=0,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["schema_version"], 3)
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["devices"]), 2)
        self.assertEqual(result["devices"][0]["width"], 2)
        self.assertEqual(result["devices"][0]["horizontal_position"], 1)
        self.assertEqual(result["devices"][1]["horizontal_position"], 2)
        self.assertEqual(result["devices"][0]["width_source"], "inferred")

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
        self.assertIn("payload?.schema_version !== 3", script)
        self.assertIn("placement.source", script)
        self.assertLess(script.index("liveViewCompatible"), script.index("netbox-utilities-partial-width"))
        self.assertLess(script.index("exportGraphic(graphic"), script.index("event.preventDefault()"))

    @patch("netbox_utilities.topology_views.topology_rack_width_enabled", return_value=True)
    def test_malformed_partial_placement_fails_open(self, _enabled):
        self.request.resolver_match = SimpleNamespace(view_name="plugins:netbox_topology_views:rack_elevation")
        with patch("dcim.models.Rack.objects.restrict", side_effect=AttributeError("stale")):
            result = get_topology_rack_width_data(self.request)

        self.assertEqual(result["status"], "native-fallback")
        self.assertEqual(result["devices"], [])
        self.assertFalse(result["complete"])

    def test_partial_width_css_uses_topology_device_slot_geometry(self):
        stylesheet = (Path(__file__).parents[1] / "static" / "netbox_utilities" / "netbox_utilities.css").read_text(
            encoding="utf-8"
        )

        self.assertIn(".rack-device.netbox-utilities-partial-width", stylesheet)
        self.assertIn("--netbox-utilities-rack-device-left", stylesheet)
        self.assertIn("--netbox-utilities-rack-device-width", stylesheet)

    def test_extracts_only_devices_rendered_by_the_authorized_topology_view(self):
        html = """
        <a class="rack-device" href="/dcim/devices/334/">Fritzbox</a>
        <a class="rack-device active" href="/dcim/devices/340/">Grandstream</a>
        <a href="/dcim/devices/999/">Not a rack device</a>
        """

        self.assertEqual(
            _visible_topology_device_urls(html),
            {334: "/dcim/devices/334/", 340: "/dcim/devices/340/"},
        )

    @patch("dcim.models.Device")
    def test_builds_both_stored_half_widths_from_visible_he11_devices(self, device_model):
        devices = [
            SimpleNamespace(
                pk=334,
                rack_id=3,
                face="front",
                position=11,
                device_type=SimpleNamespace(u_height=1),
                netbox_utilities_rack_placement=SimpleNamespace(width=2, horizontal_position=1),
                get_absolute_url=lambda: "/dcim/devices/334/",
            ),
            SimpleNamespace(
                pk=340,
                rack_id=3,
                face="front",
                position=11,
                device_type=SimpleNamespace(u_height=1),
                netbox_utilities_rack_placement=SimpleNamespace(width=2, horizontal_position=2),
                get_absolute_url=lambda: "/dcim/devices/340/",
            ),
        ]
        device_model.objects.filter.return_value.select_related.return_value.order_by.return_value = devices

        result = _topology_data_for_visible_devices({334: "/dcim/devices/334/", 340: "/dcim/devices/340/"})

        self.assertTrue(result["complete"])
        self.assertEqual(
            [(item["device_id"], item["width"], item["horizontal_position"]) for item in result["devices"]],
            [(334, 2, 1), (340, 2, 2)],
        )

    @patch("netbox_utilities.topology_views._topology_data_for_visible_devices")
    def test_injects_stored_widths_into_the_completed_foreign_response(self, get_data):
        get_data.return_value = {
            "devices": [
                {
                    "device_id": 334,
                    "url": "/dcim/devices/334/",
                    "width": 2,
                    "horizontal_position": 1,
                    "width_source": "stored",
                    "left_percent": 0,
                    "width_percent": 50,
                },
                {
                    "device_id": 340,
                    "url": "/dcim/devices/340/",
                    "width": 2,
                    "horizontal_position": 2,
                    "width_source": "stored",
                    "left_percent": 50,
                    "width_percent": 50,
                },
            ],
            "status": "ready",
            "schema_version": 3,
            "complete": True,
        }
        response = HttpResponse(
            '<html><head></head><body><a class="rack-device" href="/dcim/devices/334/">A</a>'
            '<a class="rack-device" href="/dcim/devices/340/">B</a></body></html>'
        )

        result = _inject_topology_widths(response)
        html = result.content.decode()

        get_data.assert_called_once_with({334: "/dcim/devices/334/", 340: "/dcim/devices/340/"})
        self.assertIn('id="netbox-utilities-topology-rack-width-styles"', html)
        self.assertIn('.rack-device[href="/dcim/devices/334/"]', html)
        self.assertIn("left: calc(50% + 3px) !important", html)
        self.assertIn(f"netbox_utilities/topology-rack-width.js?v={netbox_utilities.__version__}", html)
        self.assertIn("left:calc(0% + 3px)!important", html)
        self.assertIn("left:calc(50% + 3px)!important", html)
        self.assertIn("width:calc(50% - 6px)!important", html)

    def test_preserves_existing_topology_style_while_applying_width(self):
        data = {
            "devices": [
                {
                    "url": "/dcim/devices/334/",
                    "left_percent": 0,
                    "width_percent": 50,
                }
            ]
        }
        html = (
            '<a class="rack-device" href="/dcim/devices/334/" '
            'style="bottom: 10%; height: 2%; border-color: #f00">Fritzbox</a>'
        )

        result = _apply_topology_widths_to_device_tags(html, data)

        self.assertIn("bottom: 10%", result)
        self.assertIn("height: 2%", result)
        self.assertIn("left:calc(0% + 3px)!important", result)
        self.assertIn("width:calc(50% - 6px)!important", result)

    @patch("netbox_utilities.topology_views._inject_topology_widths")
    @patch("netbox_utilities.topology_views.topology_rack_width_enabled", return_value=True)
    def test_response_processor_runs_after_the_topology_view(self, _enabled, inject):
        response = HttpResponse("<html></html>")
        inject.return_value = response

        result = apply_topology_rack_widths(self.request, response)

        self.assertIs(result, response)
        inject.assert_called_once_with(response)
