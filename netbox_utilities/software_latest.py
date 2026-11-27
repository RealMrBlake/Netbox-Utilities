"""
Newest software version according to online sources, compared with the installed versions.

Sources:
- endoflife.date (https://endoflife.date/docs/api/v1/): release cycles with their latest patch version.
- Repology (https://repology.org/api): aggregates 300+ package repositories, among them winget,
  Chocolatey and Scoop, and marks the newest known upstream version.

The pure helpers (name candidates, response parsing, version comparison) carry no NetBox
dependency; lookup() adds HTTP, NetBox's HTTP_PROXIES and the Django cache.
"""

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

from .software import version_key

SOURCES = ("endoflife", "repology")
SOURCE_LABELS = {"endoflife": "endoflife.date", "repology": "Repology"}
DEFAULT_CACHE_HOURS = 24
TIMEOUT = 10
# Repositories whose packages are what Windows clients actually install.
WINDOWS_REPOS = ("winget", "chocolatey", "scoop")
# Repology asks for at most one API request per second.
REPOLOGY_INTERVAL = 1.1
# Words that describe the build, not the product: "Firefox (x64 de)", "Notepad++ 64-bit".
NOISE = re.compile(
    r"\((?:[^)]*)\)|\b(?:x64|x86|amd64|arm64|win64|win32|64-bit|32-bit|64 bit|32 bit|en-us|de-de|de|en)\b",
    re.IGNORECASE,
)
VERSION_TOKEN = re.compile(r"\bv?\d+(?:\.\d+)+\w*\b")
VENDORS = {"microsoft", "mozilla", "google", "adobe", "oracle", "videolan", "the", "apache", "igor"}

_repology_lock = threading.Lock()
_repology_last = 0.0


def clean_name(name):
    """Product name without architecture, language and version noise."""
    text = NOISE.sub(" ", str(name or ""))
    text = VERSION_TOKEN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" -_,.")


def slugify(text):
    return re.sub(r"[^a-z0-9+]+", "-", text.casefold()).strip("-")


def name_candidates(name, manufacturer=""):
    """Project names to try, most specific guess first ("Mozilla Firefox (x64 de)" -> firefox, mozilla-firefox)."""
    cleaned = clean_name(name)
    words = cleaned.split()
    vendor_words = {word.casefold() for word in str(manufacturer or "").split()} | VENDORS
    without_vendor = words
    while len(without_vendor) > 1 and without_vendor[0].casefold() in vendor_words:
        without_vendor = without_vendor[1:]
    candidates = []
    for words_variant in (without_vendor, words):
        slug = slugify(" ".join(words_variant))
        for candidate in (slug, slug.replace("-", "")):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    # Last resort: the first word ("VLC media player" -> vlc); the tooltip shows which project matched.
    if len(without_vendor) > 1 and (first := slugify(without_vendor[0])) and first not in candidates:
        candidates.append(first)
    return candidates[:5]


def numbers(version):
    return tuple(int(part) for part in re.findall(r"\d+", str(version or "")))


def compare(installed, latest):
    """
    "current", "outdated" or "unknown".

    Only the precision of the online version counts: an installed "128.0.3.8945" is current
    against "128.0.3", "127.0" is outdated against "128.0.3".
    """
    have, want = numbers(installed), numbers(latest)
    if not have or not want:
        return "unknown"
    have = (have + (0,) * len(want))[: len(want)]
    return "current" if have >= want else "outdated"


def newest(versions):
    versions = [version for version in versions if version]
    return max(versions, key=lambda version: (numbers(version), version_key(version))) if versions else None


def parse_endoflife(payload):
    """Latest patch version of a non-EOL release cycle (or of any cycle) from an /api/v1/products/<p> answer."""
    result = (payload or {}).get("result") or {}
    releases = result.get("releases") or []
    names = [(release.get("latest") or {}).get("name") for release in releases if not release.get("isEol")]
    return newest(names) or newest((release.get("latest") or {}).get("name") for release in releases)


def parse_repology(packages):
    """Newest version of a Repology project, preferring what the Windows repositories ship."""
    newest_packages = [package for package in packages or () if package.get("status") == "newest"]
    if not newest_packages:
        return None
    windows = [package for package in newest_packages if package.get("repo") in WINDOWS_REPOS]
    counts = Counter(package.get("version") for package in (windows or newest_packages) if package.get("version"))
    if not counts:
        return None
    top = max(counts.values())
    return newest(version for version, count in counts.items() if count == top)


def combine(found):
    """found: list of {"source", "version", ...}; returns the overall newest version."""
    return newest(entry["version"] for entry in found)


#
# Configuration
#


def plugin_setting(name, default):
    try:
        from netbox.plugins import get_plugin_config

        value = get_plugin_config("netbox_utilities", name)
    except Exception:  # noqa: BLE001 - outside NetBox (tests)
        value = None
    return default if value is None else value


def lookup_enabled():
    return bool(plugin_setting("software_latest_enabled", True))


def configured_sources():
    return [source for source in plugin_setting("software_latest_sources", list(SOURCES)) if source in SOURCES]


def mapping_for(name, mapping=None):
    """
    Manual project names per product, e.g. {"Mozilla Firefox": {"endoflife": "firefox", "repology": "firefox"}}.

    Keys match the product name case-insensitively; False/None as value disables the lookup.
    """
    mapping = plugin_setting("software_latest_mapping", {}) if mapping is None else mapping
    for key, value in (mapping or {}).items():
        if str(key).casefold() == str(name).casefold():
            return value if value else False
    return None


#
# HTTP
#


def user_agent():
    from . import __version__

    return f"netbox-utilities/{__version__} (software version check)"


def opener():
    handlers = []
    try:
        from django.conf import settings

        proxies = getattr(settings, "HTTP_PROXIES", None)
    except Exception:  # noqa: BLE001
        proxies = None
    if proxies:
        handlers.append(urllib.request.ProxyHandler(proxies))
    return urllib.request.build_opener(*handlers)


def fetch_json(url):
    """Parsed JSON, or None for 404. Other failures raise."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept": "application/json"})
    try:
        with opener().open(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def query_endoflife(project, fetch=fetch_json):
    payload = fetch(f"https://endoflife.date/api/v1/products/{urllib.parse.quote(project)}/")
    version = parse_endoflife(payload) if payload else None
    return {"version": version, "url": f"https://endoflife.date/{project}"} if version else None


def query_repology(project, fetch=fetch_json):
    global _repology_last
    with _repology_lock:
        wait = _repology_last + REPOLOGY_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            packages = fetch(f"https://repology.org/api/v1/project/{urllib.parse.quote(project, safe='+')}")
        finally:
            _repology_last = time.monotonic()
    version = parse_repology(packages) if packages else None
    return {"version": version, "url": f"https://repology.org/project/{project}/versions"} if version else None


QUERIES = {"endoflife": query_endoflife, "repology": query_repology}


def find_latest(name, manufacturer="", sources=None, mapping=None, fetch=fetch_json):
    """
    Ask every source for the product; returns {"latest", "found": [...], "errors": [...]}.

    Without a manual mapping the guessed names are tried one after another until a source knows one.
    """
    sources = configured_sources() if sources is None else sources
    manual = mapping_for(name, mapping)
    found, errors = [], []
    if manual is False:
        return {"latest": None, "found": [], "errors": [], "disabled": True}
    for source in sources:
        if isinstance(manual, dict):
            if not manual.get(source):
                continue
            projects = [manual[source]]
        else:
            projects = name_candidates(name, manufacturer)
        for project in projects:
            try:
                hit = QUERIES[source](project, fetch=fetch)
            except Exception as error:  # noqa: BLE001 - network problems must not break the page
                errors.append(f"{SOURCE_LABELS[source]}: {error}")
                break
            if hit:
                found.append({"source": source, "label": SOURCE_LABELS[source], "project": project, **hit})
                break
    return {"latest": combine(found), "found": found, "errors": errors}


def cache_key(name, manufacturer):
    digest = hashlib.sha1(f"{name}|{manufacturer}".casefold().encode()).hexdigest()
    return f"netbox_utilities:software_latest:{digest}"


def lookup(name, manufacturer="", refresh=False):
    """find_latest() with the Django cache; failed lookups are cached for one hour only."""
    from django.core.cache import cache
    from django.utils import timezone

    key = cache_key(name, manufacturer)
    if not refresh and (cached := cache.get(key)) is not None:
        return {**cached, "cached": True}
    result = find_latest(name, manufacturer)
    result["checked"] = timezone.now().isoformat(timespec="minutes")
    hours = float(plugin_setting("software_latest_cache_hours", DEFAULT_CACHE_HOURS))
    cache.set(key, result, int(3600 if result["errors"] and not result["found"] else hours * 3600))
    return {**result, "cached": False}
