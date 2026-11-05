from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from netbox_utilities import wireless_trace


class Interface(SimpleNamespace):
    pass


def iface(pk, device_id, wireless_link_id=None, trace=()):
    return Interface(pk=pk, device_id=device_id, wireless_link_id=wireless_link_id, trace=lambda: list(trace))


class WirelessTraceTest(SimpleTestCase):
    def setUp(self):
        # Switch port 1 --cable--> TG ether1 (10); TG wlan60 (11) ~~ Funk wlan60 (21);
        # Funk ether1 (20) --cable--> Switch2 port (30)
        self.switch_port = iface(1, 1)
        self.tg_ether = iface(10, 2)
        self.tg_wlan = iface(11, 2, wireless_link_id=99)
        self.funk_wlan = iface(21, 3, wireless_link_id=99)
        self.switch2_port = iface(30, 4)
        self.funk_ether = iface(20, 3, trace=[([iface(20, 3)], ["cable34"], [self.switch2_port])])
        self.link = SimpleNamespace(pk=99)

        def hop(device_id, visited):
            if device_id == 2 and 11 not in visited:
                return self.tg_wlan, self.link, self.funk_wlan
            if device_id == 3 and 21 not in visited:
                return self.funk_wlan, self.link, self.tg_wlan
            return None

        def cabled(device_id, visited):
            if device_id == 3 and 20 not in visited:
                return self.funk_ether
            return None

        patches = [
            patch.object(wireless_trace, "_wireless_hop", side_effect=hop),
            patch.object(wireless_trace, "_cabled_interface", side_effect=cabled),
            patch("dcim.models.Interface", Interface),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_appends_radio_hop_and_peer_cable(self):
        trace = [([self.switch_port], ["cable48"], [self.tg_ether])]

        result = wireless_trace.extended_trace(self.switch_port, trace)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[1], ([self.tg_wlan], [self.link], [self.funk_wlan]))
        self.assertEqual(result[2][1], ["cable34"])
        self.assertIs(result[2][2][0], self.switch2_port)

    def test_prepends_reversed_chain_for_radio_origin_side(self):
        trace = [([self.tg_ether], ["cable48"], [self.switch_port])]

        result = wireless_trace.extended_trace(self.tg_ether, trace)

        self.assertEqual(len(result), 3)
        self.assertIs(result[0][0][0], self.switch2_port)
        self.assertEqual(result[1], ([self.funk_wlan], [self.link], [self.tg_wlan]))
        self.assertEqual(result[2][1], ["cable48"])

    def test_empty_trace_is_left_alone(self):
        self.assertEqual(wireless_trace.extended_trace(self.tg_ether, []), [])
