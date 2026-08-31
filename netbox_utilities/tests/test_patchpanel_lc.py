from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities.patchpanel import pair_ports, port_identifier


def port(pk, name):
    return SimpleNamespace(pk=pk, name=name)


class LCPatchpanelPairingTest(SimpleTestCase):
    def test_uses_numeric_identifier_despite_connector_labels(self):
        self.assertEqual(port_identifier(port(1, "LC Front 01")), (1,))
        self.assertEqual(port_identifier(port(2, "Rear 1")), (1,))

    def test_pairs_all_six_lc_ports_by_number(self):
        front_ports = [port(number, f"LC Front {number}") for number in range(1, 7)]
        rear_ports = [port(100 + number, f"Rear {number}") for number in range(1, 7)]

        pairs = pair_ports(front_ports, rear_ports)

        self.assertEqual(
            [(front.pk, rear.pk) for front, rear in pairs],
            [(number, 100 + number) for number in range(1, 7)],
        )

    def test_keeps_compound_numeric_identifiers_distinct(self):
        front_ports = [port(12, "Cassette 1 LC 2"), port(13, "Cassette 1 LC 3")]
        rear_ports = [port(112, "Rear 1/2"), port(113, "Rear 1/3")]

        pairs = pair_ports(front_ports, rear_ports)

        self.assertEqual([(front.pk, rear.pk) for front, rear in pairs], [(12, 112), (13, 113)])
