from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities import software


def row(product, version, device, *, product_name=None, version_name=None, eos=None):
    return {
        "product_id": product,
        "product_name": product_name or f"Produkt {product}",
        "manufacturer": "Hersteller",
        "version_id": version,
        "version_name": version_name or str(version),
        "end_of_support": eos,
        "release_type": "S",
        "device_id": device,
    }


class SoftwareSummaryTest(SimpleTestCase):
    def test_counts_devices_once_and_orders_products_by_spread(self):
        summary = software.summarize(
            [
                row(1, 10, 100),
                row(1, 10, 100),  # same software recorded twice on one device
                row(2, 20, 100),
                row(2, 21, 101),
                row(2, 21, 102),
            ],
            device_total=4,
        )

        self.assertEqual([product.id for product in summary.products], [2, 1])
        self.assertEqual(summary.products[0].device_count, 3)
        self.assertEqual(summary.products[0].share, 75)
        self.assertEqual(summary.products[1].bar, 33)
        self.assertEqual(summary.installations, 5)
        self.assertEqual(summary.devices_with_software, 3)
        self.assertEqual(summary.devices_without_software, 1)
        self.assertEqual(summary.coverage, 75)
        self.assertEqual(summary.version_count, 3)

    def test_versions_are_sorted_naturally_newest_first(self):
        summary = software.summarize(
            [row(1, 1, 1, version_name="9.11"), row(1, 2, 2, version_name="10.2"), row(1, 3, 3, version_name="10.10")]
        )
        product = summary.products[0]

        self.assertEqual([version.name for version in product.versions_by_name], ["10.10", "10.2", "9.11"])
        self.assertEqual(product.latest_version.name, "10.10")
        self.assertEqual([version.shade for version in product.versions_by_name], [100, 68, 35])

    def test_expired_support_counts_affected_devices(self):
        summary = software.summarize(
            [row(1, 1, 1, eos=date(2000, 1, 1)), row(1, 2, 2), row(2, 3, 1, eos=date(2001, 1, 1))]
        )

        self.assertEqual(summary.expired_device_count, 1)
        self.assertEqual(summary.products[0].expired_devices, {1})

    def test_empty_selection(self):
        summary = software.summarize([], device_total=0)

        self.assertEqual(summary.products, [])
        self.assertEqual(summary.coverage, 0)

    def test_client_role_detection_is_case_insensitive(self):
        client = SimpleNamespace(role=SimpleNamespace(name="clients"))
        server = SimpleNamespace(role=SimpleNamespace(name="Server"))

        self.assertTrue(software.supports_software(client, roles=["Clients"]))
        self.assertFalse(software.supports_software(server, roles=["Clients"]))
        self.assertFalse(software.supports_software(SimpleNamespace(role=None), roles=["Clients"]))
