from django.test import SimpleTestCase

from netbox_utilities.software_sync import (
    UNKNOWN_VERSION,
    SoftwareEntry,
    clean_name,
    has_software_report,
    parse_software_report,
)

AGENT_REPORT = """Updated automatically by the NetBox Windows Agent.

## Hardware
- System: LENOVO 21MW

## Installed software (4)
- 7-Zip 23.01 (x64) 23.01 — Igor Pavlov
- Microsoft Visual C++ 2015-2022 Redistributable (x64) - 14.38.33130 14.38.33130.0 — Microsoft Corporation
- Microsoft Office Professional Plus 2024 — Microsoft Corporation
- Notepad++ (64-bit x64) 8.6.2
"""

SYNCHRONIZER_REPORT = """Handnotiz

<!-- netbox-sync:inventory -->
## Inventar (NetBox Windows Agent)

### Installierte Software (2)

| Programm | Version | Hersteller |
|---|---|---|
| Mozilla Firefox (x64 de) | 120.0 | Mozilla |
| Mozilla Firefox (x64 de) | 120.0 | Mozilla |
| Google Chrome | 119.0.6045.160 | Google LLC |
<!-- /netbox-sync:inventory -->
"""


class SoftwareReportParserTest(SimpleTestCase):
    def test_agent_bullets(self):
        self.assertEqual(
            parse_software_report(AGENT_REPORT),
            [
                SoftwareEntry("7-Zip 23.01 (x64)", "23.01", "Igor Pavlov"),
                SoftwareEntry(
                    "Microsoft Visual C++ 2015-2022 Redistributable (x64)", "14.38.33130.0", "Microsoft Corporation"
                ),
                SoftwareEntry("Microsoft Office Professional Plus 2024", UNKNOWN_VERSION, "Microsoft Corporation"),
                SoftwareEntry("Notepad++ (64-bit x64)", "8.6.2", ""),
            ],
        )

    def test_synchronizer_table_without_duplicates(self):
        self.assertEqual(
            parse_software_report(SYNCHRONIZER_REPORT),
            [
                SoftwareEntry("Mozilla Firefox (x64 de)", "120.0", "Mozilla"),
                SoftwareEntry("Google Chrome", "119.0.6045.160", "Google LLC"),
            ],
        )

    def test_without_report(self):
        self.assertFalse(has_software_report("Nur eine Notiz\n## Hardware"))
        self.assertEqual(parse_software_report("## Hardware\n- CPU: x"), [])
        self.assertTrue(has_software_report(AGENT_REPORT))

    def test_clean_name_strips_appended_version_only(self):
        self.assertEqual(clean_name("Foo Tool 1.2.3", "1.2.3"), "Foo Tool")
        self.assertEqual(clean_name("Bar - 14.38", "14.38.1"), "Bar")
        self.assertEqual(clean_name("Office 2024", "16.0"), "Office 2024")
