from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities import disks


def disk(**kwargs):
    defaults = {
        "status": disks.STATUS_ACTIVE,
        "capacity_gb": 1000,
        "manufacture_date": None,
        "install_date": None,
        "warranty_end": None,
    }
    return SimpleNamespace(**{**defaults, **kwargs})


class DiskRoleTest(SimpleTestCase):
    def test_configured_roles_match_case_insensitively(self):
        roles = ["Server", "NAS", "SAN", "MSA"]
        for name in ("Server", "nas", "SAN", "MSA"):
            with self.subTest(role=name):
                self.assertTrue(disks.supports_disks(SimpleNamespace(role=SimpleNamespace(name=name)), roles))

    def test_other_roles_and_missing_roles_are_rejected(self):
        roles = ["Server"]
        self.assertFalse(disks.supports_disks(SimpleNamespace(role=SimpleNamespace(name="Switch")), roles))
        self.assertFalse(disks.supports_disks(SimpleNamespace(role=None), roles))


class CapacityTest(SimpleTestCase):
    def test_parses_common_vendor_notations(self):
        cases = {
            "4 TB": 4000,
            "960GB": 960,
            "1,92 TB": 1920,
            "1.92tb": 1920,
            "4000": 4000,
            "2 TiB": 2199,
            "0,5 PB": 500000,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(disks.parse_capacity(text), expected)

    def test_empty_values_return_none(self):
        self.assertIsNone(disks.parse_capacity(""))
        self.assertIsNone(disks.parse_capacity(None))

    def test_rejects_invalid_input(self):
        for text in ("viel", "4 XB", "0 GB"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                disks.parse_capacity(text)

    def test_formats_like_vendor_labels(self):
        self.assertEqual(disks.format_capacity(960), "960 GB")
        self.assertEqual(disks.format_capacity(1920), "1,92 TB")
        self.assertEqual(disks.format_capacity(4000), "4 TB")
        self.assertEqual(disks.format_capacity(None), "—")


class RAIDCapacityTest(SimpleTestCase):
    def test_parity_levels(self):
        self.assertEqual(disks.raid_usable_capacity("raid5", [4000] * 4), (12000, 1, None))
        self.assertEqual(disks.raid_usable_capacity("raid6", [4000] * 6), (16000, 2, None))
        self.assertEqual(disks.raid_usable_capacity("raidz3", [1000] * 5), (2000, 3, None))

    def test_mirror_and_stripe_levels(self):
        self.assertEqual(disks.raid_usable_capacity("raid1", [960, 960]), (960, 1, None))
        self.assertEqual(disks.raid_usable_capacity("raid10", [1000] * 8), (4000, 1, None))
        self.assertEqual(disks.raid_usable_capacity("raid0", [1000] * 3), (3000, 0, None))
        self.assertEqual(disks.raid_usable_capacity("jbod", [1000, 2000]), (3000, 0, None))

    def test_mixed_sizes_use_smallest_member(self):
        self.assertEqual(disks.raid_usable_capacity("raid5", [4000, 4000, 2000])[0], 4000)

    def test_nested_levels_respect_spans(self):
        self.assertEqual(disks.raid_usable_capacity("raid50", [1000] * 6, spans=2)[0], 4000)
        self.assertEqual(disks.raid_usable_capacity("raid60", [1000] * 8, spans=2)[0], 4000)
        self.assertIsNotNone(disks.raid_usable_capacity("raid50", [1000] * 6, spans=1)[2])

    def test_too_few_members_report_an_error(self):
        usable, _tolerated, error = disks.raid_usable_capacity("raid6", [1000] * 3)
        self.assertIsNone(usable)
        self.assertIn("mindestens 4", error)
        self.assertIsNotNone(disks.raid_usable_capacity("raid10", [1000] * 5)[2])

    def test_empty_group(self):
        self.assertEqual(disks.raid_usable_capacity("raid5", []), (None, None, None))


class DiskWarningTest(SimpleTestCase):
    today = date(2026, 10, 19)

    def test_expired_and_expiring_warranty(self):
        expired = disks.disk_warnings(disk(warranty_end=date(2026, 1, 1)), today=self.today)
        expiring = disks.disk_warnings(disk(warranty_end=date(2026, 12, 1)), today=self.today)
        valid = disks.disk_warnings(disk(warranty_end=date(2028, 1, 1)), today=self.today)

        self.assertEqual(expired[0][0], "danger")
        self.assertEqual(expiring[0][0], "warning")
        self.assertEqual(valid, [])

    def test_age_uses_manufacture_date_before_install_date(self):
        old = disk(manufacture_date=date(2020, 1, 1), install_date=date(2024, 1, 1))
        young = disk(install_date=date(2024, 1, 1))

        self.assertIn(("warning", "Älter als 5 Jahre"), disks.disk_warnings(old, today=self.today))
        self.assertEqual(disks.disk_warnings(young, today=self.today), [])

    def test_failed_disks_warn_and_replaced_disks_never_warn(self):
        self.assertEqual(disks.disk_warnings(disk(status=disks.STATUS_FAILED), today=self.today)[0][0], "danger")
        replaced = disk(status=disks.STATUS_REPLACED, warranty_end=date(2020, 1, 1))
        self.assertEqual(disks.disk_warnings(replaced, today=self.today), [])

    def test_add_years_handles_leap_day(self):
        self.assertEqual(disks.add_years(date(2024, 2, 29), -5), date(2019, 2, 28))


class SlotGridTest(SimpleTestCase):
    def test_horizontal_numbering_fills_rows_first(self):
        grid = disks.build_slot_grid(6, rows=2, first_slot=0)

        self.assertEqual([[cell["number"] for cell in row] for row in grid], [[0, 1, 2], [3, 4, 5]])

    def test_vertical_numbering_fills_columns_first(self):
        grid = disks.build_slot_grid(6, rows=2, first_slot=1, numbering=disks.NUMBERING_VERTICAL)

        self.assertEqual([[cell["number"] for cell in row] for row in grid], [[1, 3, 5], [2, 4, 6]])

    def test_uneven_slot_counts_are_padded(self):
        grid = disks.build_slot_grid(5, rows=2)

        self.assertEqual([[cell["number"] for cell in row] for row in grid], [[0, 1, 2], [3, 4, None]])

    def test_disks_are_placed_in_their_slots(self):
        installed = disk()
        grid = disks.build_slot_grid(2, disks_by_slot={1: installed})

        self.assertIs(grid[0][1]["disk"], installed)
        self.assertIsNone(grid[0][0]["disk"])


class SerialInputTest(SimpleTestCase):
    def test_scanner_and_pasted_input(self):
        self.assertEqual(disks.parse_serials("A1\r\nB2\n\n C3 ;D4,E5\t"), ["A1", "B2", "C3", "D4", "E5"])

    def test_duplicates_are_case_insensitive(self):
        self.assertEqual(disks.duplicates(["abc", "ABC", "x", "abc"]), ["ABC"])


class SummaryTest(SimpleTestCase):
    def test_counts_and_raw_capacity_skip_planned_and_replaced(self):
        installed = [
            disk(),
            disk(status=disks.STATUS_SPARE),
            disk(status=disks.STATUS_FAILED),
            disk(status=disks.STATUS_PLANNED),
            disk(status=disks.STATUS_REPLACED),
        ]

        summary = disks.disk_summary(installed, slot_count=8)

        self.assertEqual(summary["used"], 4)
        self.assertEqual(summary["free"], 4)
        self.assertEqual(summary["raw_capacity_gb"], 3000)
        self.assertEqual(summary["spares"], 1)
        self.assertEqual(summary["failed"], 1)
