from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from netbox_utilities.patchpanel import is_patchpanel, pair_ports, port_identifier, retrace_patchpanel_paths


def port(pk, name):
    return SimpleNamespace(pk=pk, name=name)


class PatchpanelPairingTest(SimpleTestCase):
    def test_existing_device_migrations_are_noops(self):
        migration_names = (
            "0004_patchpanel_port_mappings",
            "0005_fix_patchpanel_port_number_mappings",
            "0006_retrace_existing_patchpanel_paths",
        )

        for migration_name in migration_names:
            with self.subTest(migration=migration_name):
                module = import_module(f"netbox_utilities.migrations.{migration_name}")
                self.assertEqual(module.Migration.operations, [])

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

    @patch("dcim.models.CablePath")
    def test_retraces_each_affected_cable_path_once(self, cable_path_model):
        first_path = MagicMock()
        second_path = MagicMock()

        def filter_paths(**kwargs):
            queryset = MagicMock()
            if "_nodes__contains" in kwargs:
                port_id = kwargs["_nodes__contains"].pk
                queryset.values_list.return_value = [1] if port_id == 1 else [1, 2]
            else:
                queryset.first.return_value = {1: first_path, 2: second_path}.get(kwargs["pk"])
            return queryset

        cable_path_model.objects.filter.side_effect = filter_paths

        retraced = retrace_patchpanel_paths([port(1, "Front 1"), port(2, "Front 2")])

        self.assertEqual(retraced, 2)
        first_path.retrace.assert_called_once_with()
        second_path.retrace.assert_called_once_with()
