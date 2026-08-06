from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities.patchpanel import is_patchpanel, pair_ports, port_identifier


def port(pk, name):
    return SimpleNamespace(pk=pk, name=name)


class PatchpanelPairingTest(SimpleTestCase):
    def test_detects_patchpanel_role_case_insensitively(self):
        self.assertTrue(is_patchpanel(SimpleNamespace(role=SimpleNamespace(name="Patchpanel"))))
        self.assertTrue(is_patchpanel(SimpleNamespace(role=SimpleNamespace(name="PATCHPANEL"))))
        self.assertFalse(is_patchpanel(SimpleNamespace(role=SimpleNamespace(name="Switch"))))

    def test_pairs_front_and_rear_ports_by_matching_number(self):
        front_ports = [port(10, "Front 10"), port(2, "Front 2"), port(1, "Front 1")]
        rear_ports = [port(102, "Rear 2"), port(110, "Rear 10"), port(101, "Rear 1")]

        pairs = pair_ports(front_ports, rear_ports)

        self.assertEqual([(front.pk, rear.pk) for front, rear in pairs], [(1, 101), (2, 102), (10, 110)])

    def test_leaves_unmatched_ports_without_a_mapping(self):
        pairs = pair_ports([port(1, "Front 1"), port(2, "Front 2")], [port(102, "Rear 2")])

        self.assertEqual([(front.pk, rear.pk) for front, rear in pairs], [(2, 102)])

    def test_normalizes_common_side_prefixes_and_leading_zeroes(self):
        self.assertEqual(port_identifier(port(1, "F01")), (1,))
        self.assertEqual(port_identifier(port(2, "Rear Port 1")), (1,))
        self.assertEqual(port_identifier(port(3, "FrontPort01")), (1,))

    def test_does_not_pair_different_identifiers(self):
        pairs = pair_ports([port(1, "Front 1")], [port(102, "Rear 2")])

        self.assertEqual(pairs, [])
