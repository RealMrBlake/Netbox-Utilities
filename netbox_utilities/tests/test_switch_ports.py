from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities import switch_ports
from netbox_utilities.switch_ports import Port


def port(name, **kwargs):
    return Port(pk=hash(name) & 0xFFFF, name=name, **kwargs)


class NameTest(SimpleTestCase):
    def test_split_name(self):
        self.assertEqual(switch_ports.split_name("GigabitEthernet1/0/24"), ("GigabitEthernet1/0/", 24))
        self.assertEqual(switch_ports.split_name("ethernet1/49"), ("ethernet1/", 49))
        self.assertEqual(switch_ports.split_name("Port 7"), ("Port ", 7))
        self.assertEqual(switch_ports.split_name("mgmt"), ("mgmt", None))

    def test_natural_order(self):
        names = ["Gi1/0/10", "Gi1/0/2", "Gi1/0/1"]
        self.assertEqual(sorted(names, key=switch_ports.natural_key), ["Gi1/0/1", "Gi1/0/2", "Gi1/0/10"])

    def test_optical_types(self):
        self.assertTrue(switch_ports.is_optical("10gbase-x-sfpp"))
        self.assertTrue(switch_ports.is_optical("100gbase-x-qsfp28"))
        self.assertFalse(switch_ports.is_optical("1000base-t"))

    def test_roles(self):
        self.assertTrue(switch_ports.is_switch(SimpleNamespace(role=SimpleNamespace(name="switch")), ["Switch"]))
        self.assertFalse(switch_ports.is_switch(SimpleNamespace(role=SimpleNamespace(name="Server")), ["Switch"]))


class VlanTest(SimpleTestCase):
    def test_same_vlan_same_colour(self):
        self.assertEqual(switch_ports.vlan_key("VLAN 10"), "10")
        self.assertEqual(switch_ports.vlan_key("vlan10"), "10")
        self.assertEqual(switch_ports.vlan_key("  Trunk  10,20 "), "Trunk 10,20")
        self.assertEqual(switch_ports.vlan_color("VLAN 10"), switch_ports.vlan_color("10"))
        self.assertIn(switch_ports.vlan_color("Server"), switch_ports.VLAN_PALETTE)
        self.assertIsNone(switch_ports.vlan_color(""))

    def test_legend_counts(self):
        ports = [
            port("Gi1/0/1", label="10", connected=True),
            port("Gi1/0/2", label="VLAN 10"),
            port("Gi1/0/3", label="20", connected=True),
            port("Gi1/0/4"),
            port("Po1", type="lag", label="10", virtual=True),
        ]
        legend = [(vlan, total, connected) for vlan, _, total, connected in switch_ports.vlan_legend(ports)]
        self.assertEqual(legend, [("10", 2, 1), ("20", 1, 1), ("", 1, 0)])


class LayoutTest(SimpleTestCase):
    def test_odd_top_even_bottom(self):
        ports = [port(f"Gi1/0/{number}") for number in range(1, 7)]
        group = switch_ports.build_groups(ports)[0]
        self.assertEqual([[p.number for p in column] for column in group.columns], [[1, 2], [3, 4], [5, 6]])

    def test_groups_by_member_and_medium(self):
        ports = [
            port("Gi2/0/1"),
            port("Gi1/0/1"),
            port("Te1/1/1", type="10gbase-x-sfpp"),
            port("Vlan10", type="virtual", virtual=True),
        ]
        titles = [group.title for group in switch_ports.build_groups(ports)]
        self.assertEqual(titles, ["Gi1/0", "Gi2/0", "Te1/1 (SFP)"])

    def test_single_row_without_numbers(self):
        group = switch_ports.build_groups([port("mgmt"), port("console")])
        self.assertEqual(sum(len(g.ports) for g in group), 2)

    def test_summary(self):
        ports = [
            port("1", connected=True),
            port("2"),
            port("3", enabled=False, connected=True),
            port("Po1", virtual=True, connected=True),
        ]
        self.assertEqual(
            switch_ports.summary(ports), {"total": 3, "connected": 1, "free": 1, "disabled": 1, "percent": 33}
        )
