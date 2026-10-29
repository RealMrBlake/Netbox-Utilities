from collections import Counter
from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities import cpu_catalog, hardware


class CatalogTest(SimpleTestCase):
    entries = list(cpu_catalog.entries())

    def test_covers_intel_and_amd_since_2012(self):
        self.assertGreater(len(self.entries), 600)
        self.assertEqual({entry["manufacturer"] for entry in self.entries}, {"intel", "amd"})
        self.assertEqual(min(entry["launch_year"] for entry in self.entries), 2012)

    def test_names_are_unique(self):
        names = Counter((entry["manufacturer"], entry["name"].casefold()) for entry in self.entries)
        self.assertEqual([name for name, count in names.items() if count > 1], [])

    def test_values_are_plausible(self):
        for entry in self.entries:
            with self.subTest(cpu=entry["name"]):
                self.assertIn(entry["threads"], (entry["cores"], entry["cores"] * 2))
                self.assertTrue(1 <= entry["base_clock_ghz"] <= 5)
                if entry["boost_clock_ghz"]:
                    self.assertGreaterEqual(entry["boost_clock_ghz"], entry["base_clock_ghz"])
                self.assertIn(entry["max_sockets"], (1, 2, 4, 8))

    def test_verified_samples(self):
        by_name = {entry["name"]: entry for entry in self.entries}
        samples = {
            "Xeon Gold 6338": (32, 64, 2.0, 3.2),
            "Xeon E5-2690 v4": (14, 28, 2.6, 3.5),
            "Xeon Platinum 8480+": (56, 112, 2.0, 3.8),
            "Xeon 6740E": (96, 96, 2.4, 3.2),
            "EPYC 7543": (32, 64, 2.8, 3.7),
            "EPYC 9655": (96, 192, 2.5, 4.5),
            "Opteron 6380": (16, 16, 2.5, 3.4),
        }
        for name, (cores, threads, base, boost) in samples.items():
            with self.subTest(cpu=name):
                entry = by_name[name]
                self.assertEqual(
                    (entry["cores"], entry["threads"], entry["base_clock_ghz"], entry["boost_clock_ghz"]),
                    (cores, threads, base, boost),
                )

    def test_epyc_p_models_are_single_socket(self):
        by_name = {entry["name"]: entry for entry in self.entries}
        self.assertEqual(by_name["EPYC 7402P"]["max_sockets"], 1)
        self.assertEqual(by_name["EPYC 4484PX"]["max_sockets"], 1)
        self.assertEqual(by_name["EPYC 7402"]["max_sockets"], 2)


class FormatTest(SimpleTestCase):
    def test_memory(self):
        self.assertEqual(hardware.format_memory(768), "768 GB")
        self.assertEqual(hardware.format_memory(1536), "1,5 TB")
        self.assertEqual(hardware.format_memory(12.5), "12,5 GB")
        self.assertEqual(hardware.format_memory(None), "—")

    def test_clock_and_ratio(self):
        self.assertEqual(hardware.format_clock(2.0), "2 GHz")
        self.assertEqual(hardware.format_clock(3.35), "3,35 GHz")
        self.assertEqual(hardware.format_ratio(3.25), "3,2 : 1")
        self.assertEqual(hardware.format_ratio(None), "—")


class SupportTest(SimpleTestCase):
    def test_servers_and_cluster_hosts(self):
        server = SimpleNamespace(cluster_id=None, role=SimpleNamespace(name="server"))
        host = SimpleNamespace(cluster_id=3, role=SimpleNamespace(name="Hypervisor"))
        switch = SimpleNamespace(cluster_id=None, role=SimpleNamespace(name="Switch"))
        self.assertTrue(hardware.supports_hardware(server, ["Server"]))
        self.assertTrue(hardware.supports_hardware(host, ["Server"]))
        self.assertFalse(hardware.supports_hardware(switch, ["Server"]))


class CapacityTest(SimpleTestCase):
    def hosts(self):
        return [
            hardware.Host("esx01", cores=32, threads=64, memory_gb=512),
            hardware.Host("esx02", cores=32, threads=64, memory_gb=512),
            hardware.Host("esx03", cores=32, threads=64, memory_gb=768),
        ]

    def test_totals_ratio_and_failover(self):
        vms = [
            ("esx01", 8, 64 * 1024, "active"),
            ("esx02", 16, 128 * 1024, "active"),
            (None, 4, 32 * 1024, "planned"),
            ("esx03", 64, 512 * 1024, "offline"),
        ]
        capacity = hardware.build_capacity(self.hosts(), vms)
        self.assertEqual((capacity.cores, capacity.threads, capacity.memory_gb), (96, 192, 1792))
        self.assertEqual((capacity.vm_count, capacity.vcpus, capacity.vm_memory_gb), (3, 28, 224))
        self.assertEqual(capacity.unplaced_vm_count, 1)
        self.assertAlmostEqual(capacity.vcpu_per_core, 28 / 96)
        self.assertEqual(capacity.memory_percent, 12)
        self.assertEqual(capacity.failover_memory_gb, 1024)
        self.assertTrue(capacity.failover_ok)
        self.assertEqual(capacity.warnings(), [])
        self.assertEqual(capacity.hosts[0].vcpus, 8)

    def test_warnings(self):
        hosts = [*self.hosts(), hardware.Host("esx04")]
        vms = [("esx01", 600, 1200 * 1024, "active")]
        levels = [level for level, _ in hardware.build_capacity(hosts, vms).warnings(ratio_warning=4)]
        self.assertEqual(levels, ["warning", "warning", "warning"])
        vms = [("esx01", 8, 2000 * 1024, "active")]
        texts = [text for _, text in hardware.build_capacity(self.hosts(), vms).warnings()]
        self.assertIn("Die VMs haben mehr RAM zugewiesen, als die Hosts haben.", texts)

    def test_single_host_has_no_failover(self):
        capacity = hardware.build_capacity(self.hosts()[:1], [])
        self.assertIsNone(capacity.failover_memory_gb)
        self.assertEqual(capacity.vcpu_per_core, 0)
