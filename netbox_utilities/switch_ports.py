"""Pure helpers for the "Ports" tab of switches: grouping, front-panel layout and VLAN colours."""

import hashlib
import re
from dataclasses import dataclass, field

DEFAULT_SWITCH_DEVICE_ROLES = ("Switch",)

# Peer text of interfaces that are only marked as connected; translated in the export.
MARKED_CONNECTED = "__marked__"

STATE_CONNECTED = "connected"
STATE_FREE = "free"
STATE_DISABLED = "disabled"
STATE_LABELS = {
    STATE_CONNECTED: "Belegt",
    STATE_FREE: "Frei",
    STATE_DISABLED: "Deaktiviert",
}

# Interface types that are not physical front ports.
VIRTUAL_TYPES = ("virtual", "lag", "bridge")
OPTICAL_MARKERS = ("sfp", "qsfp", "xfp", "x2", "cfp", "osfp", "gbic")

# Distinct background colours for VLAN labels; the text colour is chosen per colour for contrast.
VLAN_PALETTE = (
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#d62728",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#17becf",  # cyan
    "#bcbd22",  # olive
    "#7f7f7f",  # grey
    "#393b79",  # navy
    "#ffbb78",  # light orange
    "#98df8a",  # light green
    "#c5b0d5",  # lavender
    "#f7b6d2",  # rose
    "#9edae5",  # light cyan
)

# Texts of the front panel on the device page, by NetBox user language.
PANEL_TEXTS = {
    "de": {
        "title": "Ports",
        "status": "Status",
        "vlan": "VLAN",
        "connected": "Belegt",
        "free": "Frei",
        "disabled": "Deaktiviert",
        "no_label": "ohne Label",
        "ports": "Ports",
        "export": "PDF exportieren",
        "peer": "Gegenstelle",
        "marked": "als verbunden markiert",
        "none": "Keine physischen Schnittstellen.",
    },
    "en": {
        "title": "Ports",
        "status": "Status",
        "vlan": "VLAN",
        "connected": "Connected",
        "free": "Free",
        "disabled": "Disabled",
        "no_label": "no label",
        "ports": "ports",
        "export": "Export PDF",
        "peer": "Peer",
        "marked": "marked as connected",
        "none": "No physical interfaces.",
    },
}

_NAME_PATTERN = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")
_NATURAL = re.compile(r"(\d+)")


def configured_roles(roles=None):
    if roles is None:
        try:
            from netbox.plugins import get_plugin_config

            roles = get_plugin_config("netbox_utilities", "switch_device_roles")
        except Exception:  # noqa: BLE001 - outside NetBox (tests) fall back to defaults
            roles = None
    return {str(role).casefold() for role in (roles if roles is not None else DEFAULT_SWITCH_DEVICE_ROLES)}


def is_switch(device, roles=None):
    role = getattr(device, "role", None)
    return bool(role and str(getattr(role, "name", "")).casefold() in configured_roles(roles))


def natural_key(text):
    """ "Gi1/0/10" sorts after "Gi1/0/9"."""
    return [int(part) if part.isdigit() else part.casefold() for part in _NATURAL.split(text or "")]


def split_name(name):
    """("GigabitEthernet1/0/", 24) for "GigabitEthernet1/0/24"; (name, None) without a trailing number."""
    match = _NAME_PATTERN.match(name or "")
    if not match:
        return name or "", None
    return match.group("prefix"), int(match.group("number"))


def is_optical(interface_type):
    text = (interface_type or "").casefold()
    return any(marker in text for marker in OPTICAL_MARKERS)


def vlan_key(label):
    """Normalised VLAN label so that "VLAN 10", "vlan10" and "10" get the same colour."""
    text = re.sub(r"\s+", " ", (label or "").strip())
    match = re.fullmatch(r"(?i)vlan\s*(\d+)", text)
    return match.group(1) if match else text


def ink_for(hex_color):
    """ "#000000" or "#ffffff", whichever has the higher WCAG contrast against the colour."""
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))

    def channel(component):
        return component / 12.92 if component <= 0.03928 else ((component + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)
    return "#000000" if (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) else "#ffffff"


def vlan_color(label):
    key = vlan_key(label)
    if not key:
        return None
    digest = hashlib.md5(key.casefold().encode("utf-8"), usedforsecurity=False).digest()
    return VLAN_PALETTE[digest[0] % len(VLAN_PALETTE)]


@dataclass
class Port:
    pk: int
    name: str
    label: str = ""
    type: str = ""
    type_display: str = ""
    enabled: bool = True
    connected: bool = False
    mgmt_only: bool = False
    description: str = ""
    peer: str = ""
    peer_url: str = ""
    lag: str = ""
    speed: str = ""
    url: str = ""
    virtual: bool = False
    # Set by assign_vlan_colors(); otherwise the colour comes from a hash of the label.
    assigned_color: str = ""
    # Translated status for tooltips, set by the view.
    state_text: str = ""

    @property
    def state(self):
        if not self.enabled:
            return STATE_DISABLED
        return STATE_CONNECTED if self.connected else STATE_FREE

    @property
    def state_label(self):
        return STATE_LABELS[self.state]

    @property
    def number(self):
        return split_name(self.name)[1]

    @property
    def short(self):
        """Text inside the tile: the port number, or the name if it has none."""
        number = self.number
        return str(number) if number is not None else self.name

    @property
    def vlan(self):
        return vlan_key(self.label)

    @property
    def ink(self):
        """Text colour (black or white) that contrasts best with the VLAN colour."""
        return ink_for(self.color) if self.color else ""

    @property
    def color(self):
        if not self.vlan:
            return None
        return self.assigned_color or vlan_color(self.label)


@dataclass
class PortGroup:
    """Ports with the same name prefix, e.g. one stack member or line card."""

    title: str
    optical: bool
    ports: list = field(default_factory=list)

    @property
    def columns(self):
        """Front-panel layout: odd numbers on top, even numbers below, like most switches."""
        ports = sorted(self.ports, key=lambda port: (port.number is None, port.number or 0, natural_key(port.name)))
        numbered = all(port.number is not None for port in ports)
        if numbered and len(ports) > 1:
            top = [port for port in ports if port.number % 2 == 1]
            bottom = [port for port in ports if port.number % 2 == 0]
            if top and bottom and abs(len(top) - len(bottom)) <= 1:
                return [[port for port in pair if port] for pair in _zip_longest(top, bottom)]
        return [[port] for port in ports]


def _zip_longest(top, bottom):
    for index in range(max(len(top), len(bottom))):
        yield (top[index] if index < len(top) else None, bottom[index] if index < len(bottom) else None)


def build_groups(ports):
    """Physical ports grouped by name prefix and medium, in natural order."""
    groups = {}
    for port in ports:
        if port.virtual:
            continue
        prefix, _ = split_name(port.name)
        optical = is_optical(port.type)
        key = (prefix, optical)
        if key not in groups:
            title = prefix.rstrip("/:-. ") or "Ports"
            groups[key] = PortGroup(title=f"{title} (SFP)" if optical else title, optical=optical)
        groups[key].ports.append(port)
    return sorted(groups.values(), key=lambda group: (natural_key(group.title), group.optical))


def summary(ports):
    physical = [port for port in ports if not port.virtual]
    total = len(physical)
    connected = sum(1 for port in physical if port.state == STATE_CONNECTED)
    disabled = sum(1 for port in physical if port.state == STATE_DISABLED)
    return {
        "total": total,
        "connected": connected,
        "free": total - connected - disabled,
        "disabled": disabled,
        "percent": round(connected / total * 100) if total else 0,
    }


def assign_vlan_colors(ports):
    """Give every VLAN of one switch its own palette colour (in natural order), so no two collide.

    Only with more VLANs than palette colours do the remaining ones fall back to the hash colour.
    """
    vlans = sorted({port.vlan for port in ports if port.vlan}, key=natural_key)
    colors = {vlan: VLAN_PALETTE[index] for index, vlan in enumerate(vlans[: len(VLAN_PALETTE)])}
    for port in ports:
        if port.vlan:
            port.assigned_color = colors.get(port.vlan, "")
    return colors


def vlan_legend(ports):
    """[(vlan, colour, port count, connected count)] sorted naturally; unlabelled ports last."""
    counts = {}
    colors = {}
    for port in ports:
        if port.virtual:
            continue
        colors.setdefault(port.vlan, port.color)
        entry = counts.setdefault(port.vlan, [0, 0])
        entry[0] += 1
        entry[1] += port.state == STATE_CONNECTED
    legend = [(vlan, colors[vlan], total, connected) for vlan, (total, connected) in counts.items() if vlan]
    legend.sort(key=lambda item: natural_key(item[0]))
    if "" in counts:
        legend.append(("", None, counts[""][0], counts[""][1]))
    return legend
