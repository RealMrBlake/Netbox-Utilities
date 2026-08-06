from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities.patchpanel import is_patchpanel, pair_ports


def port(pk, name):
    return SimpleNamespace(pk=pk, name=name)


class PatchpanelPairingTest(SimpleTestCase):
    def test_detects_patchpanel_role_case_insensitively(self):
        self.assertTrue(is_patchpanel(SimpleNamespace(role=SimpleNamespace(name="Patchpanel"))))
        self.assertTrue(is_patchpanel(SimpleNamespace(role=SimpleNamespace(name="PATCHPANEL"))))
        self.assertFalse(is_patchpanel(SimpleNamespace(role=SimpleNamespace(name="Switch"))))

    def test_pairs_front_and_rear_ports_in_natural_order(self):
        front_ports = [port(10, "10"), port(2, "2"), port(1, "1")]
        rear_ports = [port(102, "Rear 2"), port(110, "Rear 10"), port(101, "Rear 1")]

        pairs = pair_ports(front_ports, rear_ports)

        self.assertEqual([(front.pk, rear.pk) for front, rear in pairs], [(1, 101), (2, 102), (10, 110)])

    def test_leaves_unmatched_ports_without_a_mapping(self):
        pairs = pair_ports([port(1, "1"), port(2, "2")], [port(101, "1")])

        self.assertEqual([(front.pk, rear.pk) for front, rear in pairs], [(1, 101)])
