from django.test import SimpleTestCase

from netbox_utilities import software_latest as latest


class NameCandidatesTest(SimpleTestCase):
    def test_strips_vendor_architecture_language_and_version(self):
        self.assertEqual(
            latest.name_candidates("Mozilla Firefox (x64 de)", "Mozilla"),
            ["firefox", "mozilla-firefox", "mozillafirefox"],
        )
        self.assertEqual(latest.name_candidates("7-Zip 23.01 (x64)")[:2], ["7-zip", "7zip"])
        self.assertEqual(latest.name_candidates("Notepad++ (64-bit x64)")[0], "notepad++")
        self.assertEqual(latest.name_candidates("VLC media player", "VideoLAN")[0], "vlc-media-player")
        self.assertEqual(latest.name_candidates("VLC media player", "VideoLAN")[-1], "vlc")

    def test_single_word_is_kept_even_if_it_is_a_vendor(self):
        self.assertEqual(latest.name_candidates("Google")[0], "google")


class CompareTest(SimpleTestCase):
    def test_precision_of_online_version_counts(self):
        self.assertEqual(latest.compare("128.0.3.8945", "128.0.3"), "current")
        self.assertEqual(latest.compare("128.0", "128.0.3"), "outdated")
        self.assertEqual(latest.compare("129.0", "128.0.3"), "current")
        self.assertEqual(latest.compare("9.11", "10.2"), "outdated")
        self.assertEqual(latest.compare("unbekannt", "10.2"), "unknown")

    def test_newest_is_numeric(self):
        self.assertEqual(latest.newest(["9.11", "10.2", "10.10", None]), "10.10")


class ParseTest(SimpleTestCase):
    def test_endoflife_prefers_supported_cycles(self):
        payload = {
            "result": {
                "releases": [
                    {"name": "esr", "isEol": False, "latest": {"name": "128.5.0"}},
                    {"name": "133", "isEol": False, "latest": {"name": "133.0.3"}},
                    {"name": "old", "isEol": True, "latest": {"name": "200.0"}},
                ]
            }
        }
        self.assertEqual(latest.parse_endoflife(payload), "133.0.3")
        self.assertIsNone(latest.parse_endoflife({"result": {"releases": []}}))

    def test_repology_prefers_windows_repositories(self):
        packages = [
            {"repo": "arch", "version": "24.09", "status": "newest"},
            {"repo": "debian", "version": "24.09", "status": "newest"},
            {"repo": "winget", "version": "24.08", "status": "newest"},
            {"repo": "chocolatey", "version": "24.08", "status": "newest"},
            {"repo": "ubuntu", "version": "23.01", "status": "outdated"},
        ]
        self.assertEqual(latest.parse_repology(packages), "24.08")
        self.assertEqual(latest.parse_repology(packages[:2]), "24.09")
        self.assertIsNone(latest.parse_repology([{"repo": "x", "version": "1", "status": "outdated"}]))


class FindLatestTest(SimpleTestCase):
    def fake_fetch(self, answers):
        calls = []

        def fetch(url):
            calls.append(url)
            for fragment, answer in answers.items():
                if fragment in url:
                    if isinstance(answer, Exception):
                        raise answer
                    return answer
            return None

        return fetch, calls

    def test_tries_candidates_and_combines_sources(self):
        latest.REPOLOGY_INTERVAL = 0
        fetch, calls = self.fake_fetch(
            {
                "endoflife.date/api/v1/products/firefox/": {
                    "result": {"releases": [{"isEol": False, "latest": {"name": "133.0.3"}}]}
                },
                "repology.org/api/v1/project/firefox": [{"repo": "winget", "version": "133.0.3", "status": "newest"}],
            }
        )
        result = latest.find_latest(
            "Mozilla Firefox (x64 de)", "Mozilla", sources=["endoflife", "repology"], mapping={}, fetch=fetch
        )

        self.assertEqual(result["latest"], "133.0.3")
        self.assertEqual([hit["source"] for hit in result["found"]], ["endoflife", "repology"])
        self.assertEqual(len(calls), 2)

    def test_manual_mapping_and_disabling(self):
        fetch, calls = self.fake_fetch(
            {"products/chrome/": {"result": {"releases": [{"isEol": False, "latest": {"name": "131.0.6778.86"}}]}}}
        )
        mapping = {"google chrome": {"endoflife": "chrome"}, "Intern Tool": False}

        result = latest.find_latest("Google Chrome", sources=["endoflife", "repology"], mapping=mapping, fetch=fetch)
        self.assertEqual(result["latest"], "131.0.6778.86")
        self.assertEqual(len(calls), 1)  # repology has no mapping entry and is skipped

        self.assertTrue(latest.find_latest("Intern Tool", mapping=mapping, fetch=fetch)["disabled"])

    def test_network_errors_are_reported_not_raised(self):
        fetch, _ = self.fake_fetch({"endoflife": OSError("timeout")})
        result = latest.find_latest("Firefox", sources=["endoflife"], mapping={}, fetch=fetch)

        self.assertIsNone(result["latest"])
        self.assertIn("endoflife.date: timeout", result["errors"])
