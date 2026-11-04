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


class ColorAssignmentTest(SimpleTestCase):
    def test_every_vlan_gets_its_own_colour(self):
        ports = [
            port(f"Gi1/0/{index}", label=label) for index, label in enumerate(["10", "VLAN 10", "20", "Trunk", ""])
        ]
        colors = switch_ports.assign_vlan_colors(ports)
        self.assertEqual(len(set(colors.values())), 3)
        self.assertEqual(ports[0].color, ports[1].color)
        self.assertIsNone(ports[4].color)


class PDFTest(SimpleTestCase):
    def ports(self):
        return [
            port("Gi1/0/1", label="10", connected=True, peer="srv1 – eth0"),
            port("Gi1/0/2", label="20"),
            port("Gi1/0/3", enabled=False),
            port("Te1/1/1", type="10gbase-x-sfpp", label="Trunk", connected=True, peer=switch_ports.MARKED_CONNECTED),
            port("Po1", type="lag", virtual=True),
        ]

    def test_builds_pdf_in_both_languages(self):
        from netbox_utilities import switch_port_pdf

        device = switch_port_pdf.DeviceInfo(name="sw1", site="HQ", rack="R1 / U10", model="C9300")
        for lang in ("de", "en"):
            with self.subTest(lang=lang):
                data = switch_port_pdf.build_pdf(device, self.ports(), lang=lang)
                self.assertTrue(data.startswith(b"%PDF"))
                self.assertGreater(len(data), 2000)

    def test_language_follows_user_setting(self):
        from netbox_utilities import switch_port_pdf

        self.assertEqual(switch_port_pdf.language("en-us"), "en")
        self.assertEqual(switch_port_pdf.language("de"), "de")
        self.assertEqual(switch_port_pdf.language(None), "de")

    def test_text_contrasts_with_fill(self):
        from reportlab.lib import colors

        from netbox_utilities import switch_port_pdf

        self.assertEqual(switch_port_pdf.text_color(colors.HexColor("#ff7f0e")), colors.black)
        self.assertEqual(switch_port_pdf.text_color(colors.HexColor("#2ca02c")), colors.black)
        self.assertEqual(switch_port_pdf.text_color(colors.HexColor("#1f77b4")), colors.white)
        self.assertEqual(switch_port_pdf.text_color(colors.HexColor("#393b79")), colors.white)
        for color in switch_ports.VLAN_PALETTE:
            with self.subTest(color=color):
                fill = colors.HexColor(color)
                ink = switch_port_pdf.text_color(fill)
                light, dark = sorted((switch_port_pdf.luminance(fill), switch_port_pdf.luminance(ink)), reverse=True)
                self.assertGreaterEqual((light + 0.05) / (dark + 0.05), 3)


class InkTest(SimpleTestCase):
    def test_text_colour_contrasts_with_vlan_colour(self):
        self.assertEqual(switch_ports.ink_for("#ff7f0e"), "#000000")
        self.assertEqual(switch_ports.ink_for("#1f77b4"), "#ffffff")
        self.assertEqual(port("1", label="10", assigned_color="#2ca02c").ink, "#000000")
        self.assertEqual(port("2").ink, "")


class ManagementTest(SimpleTestCase):
    def test_management_ports_are_abbreviated_and_grouped_last(self):
        ports = [port("Management"), port("Gi1/0/1"), port("mgmt0"), port("oobm"), port("eth0", mgmt_only=True)]
        self.assertEqual([p.short for p in ports], ["MGMT", "1", "MGMT", "MGMT", "MGMT"])
        groups = switch_ports.build_groups(ports)
        self.assertEqual([group.title for group in groups], ["Gi1/0", "Management"])
        self.assertEqual(len(groups[-1].ports), 4)

    def test_other_ports_without_number_are_shortened(self):
        self.assertEqual(port("console").short, "conso")


class CableVlanTest(SimpleTestCase):
    def test_cable_vlans_are_used_without_label(self):
        p = port("Gi1/0/1", cable_vlans=[(20, "VoIP"), (10, "Office")])
        self.assertEqual(p.vlan, "10, 20")
        self.assertEqual(p.cable_vlan_text, "10 Office, 20 VoIP")
        self.assertFalse(p.vlan_mismatch)

    def test_label_wins_and_cable_vlan_shares_its_colour(self):
        labelled = port("Gi1/0/1", label="VLAN 10", cable_vlans=[(10, "Office")])
        cable_only = port("Gi1/0/2", cable_vlans=[(10, "Office")])
        switch_ports.assign_vlan_colors([labelled, cable_only])
        self.assertEqual(labelled.vlan, "10")
        self.assertEqual(labelled.color, cable_only.color)
        self.assertFalse(labelled.vlan_mismatch)

    def test_mismatch_only_for_numeric_labels(self):
        self.assertTrue(port("1", label="20", cable_vlans=[(30, "")]).vlan_mismatch)
        self.assertTrue(port("2", label="Server 30", cable_vlans=[(30, ""), (40, "")]).vlan_mismatch)
        self.assertFalse(port("3", label="Trunk", cable_vlans=[(30, "")]).vlan_mismatch)
        self.assertFalse(port("4", label="10,20", cable_vlans=[(20, ""), (10, "")]).vlan_mismatch)


class VlanIdentityTest(SimpleTestCase):
    def test_label_number_and_cable_vlan_are_one_vlan(self):
        ports = [
            port("1", label="Server 30", connected=True),
            port("2", label="VLAN 30"),
            port("3", cable_vlans=[(30, "Server")], connected=True),
            port("4", label="Trunk"),
            port("5", label="10,20"),
        ]
        switch_ports.assign_vlan_colors(ports)
        self.assertEqual(len({p.color for p in ports[:3]}), 1)
        legend = [(text, total, connected) for text, _, total, connected in switch_ports.vlan_legend(ports)]
        self.assertEqual(legend, [("10,20", 1, 0), ("Server 30", 3, 2), ("Trunk", 1, 0)])

    def test_lag_note_in_label_is_no_vlan(self):
        lag = port("1", label="30 (LAG 1)", cable_vlans=[(30, "")])
        self.assertEqual((lag.vlan, lag.vlan_group, lag.vlan_mismatch), ("30", "30", False))
        trunk = port("2", label="10,20 (LAG 2)")
        self.assertEqual(trunk.vlan_group, "10,20")
        self.assertEqual(port("3", label="(LAG 1)").vlan, "")
