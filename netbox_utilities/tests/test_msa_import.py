from types import SimpleNamespace

from django.test import SimpleTestCase

from netbox_utilities import disks, msa_import

EXPORT = """Location,Health,Type,Size,Usage,Disk Group,Status,Serial Number,r/min,Manufacturer,Model,Revision,Power On Hours,FDE State,FDE Lock Key,Sector Format
1.1,OK,SSD SAS,745.2GiB,VIRTUAL POOL,rcA1,Up,Z8713PT50000822150Z3,0k,SEAGATE,ST800FM0403,0007,70425,Not FDE Capable,00000000,512e
1.11,OK,SAS,558.9GiB,GLOBAL SP,-,Up,X4T0A00LFJVL,10k,HPE,EG000600JWJNH,HPD5,1803,Not FDE Capable,00000000,512n
1.3,Fault,SAS,558.9GiB,VIRTUAL POOL,dgA01,Up,WFJ0KKMY,10k,HP,EG000600JWJNP,HPD1,70425,Not FDE Capable,00000000,512n
2.1,OK,SAS,558.9GiB,VIRTUAL POOL,dgB01,Up,WFJ0KGPR,10k,HP,EG000600JWJNP,HPD1,70425,Not FDE Capable,00000000,512n
"""


class ParseExportTest(SimpleTestCase):
    def test_parses_enclosures_slots_and_fields(self):
        export = msa_import.parse_export(EXPORT.encode("utf-8"))
        self.assertEqual(export.errors, [])
        enclosures = export.enclosures
        self.assertEqual(list(enclosures), ["1", "2"])
        self.assertEqual([disk.slot for disk in enclosures["1"]], [1, 3, 11])

        ssd = enclosures["1"][0]
        self.assertEqual((ssd.disk_type, ssd.interface), ("ssd", "sas"))
        self.assertEqual(ssd.capacity_gb, 800)
        self.assertEqual(ssd.disk_group, "rcA1")
        self.assertEqual(ssd.firmware, "0007")
        self.assertEqual(ssd.power_on_hours, 70425)
        self.assertEqual(ssd.status, disks.STATUS_ACTIVE)

    def test_maps_spares_failed_disks_and_missing_groups(self):
        by_slot = {disk.slot: disk for disk in msa_import.parse_export(EXPORT).enclosures["1"]}
        self.assertEqual(by_slot[11].status, disks.STATUS_SPARE)
        self.assertEqual(by_slot[11].disk_group, "")
        self.assertEqual(by_slot[3].status, disks.STATUS_FAILED)
        self.assertEqual((by_slot[3].disk_type, by_slot[3].capacity_gb), ("hdd", 600))

    def test_semicolon_csv_from_excel(self):
        text = "Location;Type;Serial Number\n1.4;SATA;ABC\n"
        disk = msa_import.parse_export(text).disks[0]
        self.assertEqual((disk.enclosure, disk.slot, disk.serial, disk.interface), ("1", 4, "ABC", "sata"))

    def test_rejects_other_files_and_bad_rows(self):
        self.assertTrue(msa_import.parse_export("Name,Serial\nfoo,bar\n").errors)
        export = msa_import.parse_export("Location\n1.x\n1.2\n1.2\n")
        self.assertEqual(len(export.disks), 1)
        self.assertEqual(len(export.errors), 2)


class SuggestionTest(SimpleTestCase):
    def test_slot_count_rounds_up_to_enclosure_sizes(self):
        self.assertEqual(msa_import.suggest_slot_count(11), 12)
        self.assertEqual(msa_import.suggest_slot_count(21), 24)
        self.assertEqual(msa_import.suggest_slot_count(30), 30)
        self.assertEqual(msa_import.suggest_form_factor(24), "2.5")


class ClassifyTest(SimpleTestCase):
    disk = SimpleNamespace(slot=4, serial="ABC")

    def test_free_slot_is_new(self):
        self.assertEqual(msa_import.classify(self.disk, 1, 24)[0], msa_import.ACTION_NEW)

    def test_same_serial_updates(self):
        self.assertEqual(msa_import.classify(self.disk, 1, 24, occupant_serial="abc")[0], msa_import.ACTION_UPDATE)

    def test_other_disk_is_skipped_or_replaced(self):
        self.assertEqual(msa_import.classify(self.disk, 1, 24, occupant_serial="XYZ")[0], msa_import.ACTION_SKIP)
        self.assertEqual(
            msa_import.classify(self.disk, 1, 24, occupant_serial="XYZ", replace=True)[0], msa_import.ACTION_REPLACE
        )

    def test_conflicts(self):
        self.assertEqual(msa_import.classify(self.disk, 1, 3)[0], msa_import.ACTION_CONFLICT)
        self.assertEqual(
            msa_import.classify(self.disk, 1, 24, serial_elsewhere="MSA2 – Front 7")[0], msa_import.ACTION_CONFLICT
        )
