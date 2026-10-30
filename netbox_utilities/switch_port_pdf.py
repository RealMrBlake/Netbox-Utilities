"""PDF export of a switch's port usage: front panel coloured by VLAN label plus the full port list.

Pure ReportLab code without NetBox imports, so it can be tested on its own.
"""

import io
import math
from dataclasses import dataclass, field
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import CondPageBreak

from . import switch_ports

TEXTS = {
    "de": {
        "title": "Switch-Belegung",
        "generated": "Stand",
        "page": "Seite",
        "ports": "Ports",
        "connected": "Belegt",
        "free": "Frei",
        "disabled": "Deaktiviert",
        "front": "Frontansicht",
        "legend_state": "Kräftige Farbe mit dickem Rahmen = belegt · blasse Farbe = frei · gestrichelt mit ✕ = deaktiviert",
        "legend_vlan": "VLANs (Label)",
        "no_label": "ohne Label",
        "list": "Alle Schnittstellen",
        "port": "Port",
        "status": "Status",
        "vlan": "VLAN (Label)",
        "peer": "Gegenstelle",
        "description": "Beschreibung",
        "type": "Typ",
        "lag": "LAG",
        "marked": "als verbunden markiert",
        "none": "Keine physischen Schnittstellen.",
        "site": "Standort",
        "rack": "Rack",
        "model": "Modell",
        "mgmt": "Mgmt",
        "date_format": "%d.%m.%Y %H:%M",
        "button": "Switch-Belegung exportieren",
        "filename": "Switch-Belegung",
    },
    "en": {
        "title": "Switch port usage",
        "generated": "As of",
        "page": "Page",
        "ports": "Ports",
        "connected": "Connected",
        "free": "Free",
        "disabled": "Disabled",
        "front": "Front panel",
        "legend_state": "Strong colour with thick border = connected · pale colour = free · dashed with ✕ = disabled",
        "legend_vlan": "VLANs (label)",
        "no_label": "no label",
        "list": "All interfaces",
        "port": "Port",
        "status": "Status",
        "vlan": "VLAN (label)",
        "peer": "Peer",
        "description": "Description",
        "type": "Type",
        "lag": "LAG",
        "marked": "marked as connected",
        "none": "No physical interfaces.",
        "site": "Site",
        "rack": "Rack",
        "model": "Model",
        "mgmt": "Mgmt",
        "date_format": "%Y-%m-%d %H:%M",
        "button": "Export switch port usage",
        "filename": "switch-port-usage",
    },
}

PAGE = A4
MARGIN = 12 * mm
TILE_W = 12.5 * mm
TILE_H = 9.5 * mm
TILE_GAP = 1.2 * mm
OPTICAL_W = 13.5 * mm
FREE_FILL = colors.white
UNLABELLED_FILL = colors.HexColor("#e9ecef")
BORDER_DARK = colors.HexColor("#212529")
BORDER_LIGHT = colors.HexColor("#adb5bd")


def language(code):
    return "en" if (code or "").lower().startswith("en") else "de"


def luminance(color):
    """WCAG relative luminance of a ReportLab colour."""

    def channel(value):
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.red) + 0.7152 * channel(color.green) + 0.0722 * channel(color.blue)


def text_color(fill):
    """Black or white text, whichever has the higher WCAG contrast ratio against the fill."""
    value = luminance(fill)
    against_black = (value + 0.05) / 0.05
    against_white = 1.05 / (value + 0.05)
    return colors.black if against_black >= against_white else colors.white


def tint(color, amount=0.6):
    """Mix a colour with white; free ports use a pale version of their VLAN colour."""
    return colors.Color(*(channel + (1 - channel) * amount for channel in (color.red, color.green, color.blue)))


def hex_of(color):
    return "#{:02x}{:02x}{:02x}".format(*(round(channel * 255) for channel in (color.red, color.green, color.blue)))


def tile_fill(port):
    """Full VLAN colour for used ports, a pale one for free and disabled ports."""
    base = colors.HexColor(port.color) if port.color else UNLABELLED_FILL
    if port.state == switch_ports.STATE_CONNECTED:
        return base
    return tint(base) if port.color else FREE_FILL


@dataclass
class DeviceInfo:
    name: str
    site: str = ""
    rack: str = ""
    model: str = ""
    extra: list = field(default_factory=list)


class PortPanel(Flowable):
    """One group of ports (stack member / line card) drawn like the device front."""

    def __init__(self, columns, optical, width, tile_w):
        super().__init__()
        self.columns = columns
        self.optical = optical
        self.tile_w = tile_w
        self.rows = max((len(column) for column in columns), default=1)
        self.width = width
        self.height = self.rows * TILE_H + (self.rows - 1) * TILE_GAP + 2 * TILE_GAP

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        used = len(self.columns) * (self.tile_w + TILE_GAP) + TILE_GAP
        canvas.setFillColor(colors.HexColor("#f1f3f5"))
        canvas.setStrokeColor(BORDER_LIGHT)
        canvas.roundRect(0, 0, used, self.height, 1.5 * mm, stroke=1, fill=1)
        for index, column in enumerate(self.columns):
            x = TILE_GAP + index * (self.tile_w + TILE_GAP)
            for row, port in enumerate(column):
                y = self.height - TILE_GAP - (row + 1) * TILE_H - row * TILE_GAP
                self.draw_tile(port, x, y)

    def draw_tile(self, port, x, y):
        canvas = self.canv
        fill = tile_fill(port)
        connected = port.state == switch_ports.STATE_CONNECTED
        disabled = port.state == switch_ports.STATE_DISABLED
        canvas.setFillColor(fill)
        canvas.setStrokeColor(BORDER_DARK if connected else BORDER_LIGHT)
        canvas.setLineWidth(1.6 if connected else 0.7)
        if disabled:
            canvas.setDash(1.2, 1.2)
        radius = 0.4 * mm if self.optical else 1 * mm
        canvas.roundRect(x, y, self.tile_w, TILE_H, radius, stroke=1, fill=1)
        canvas.setDash()

        ink = text_color(fill)
        canvas.setFillColor(ink)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawCentredString(x + self.tile_w / 2, y + TILE_H - 3.4 * mm, port.short[:6])
        if port.vlan:
            canvas.setFont("Helvetica", 5.5)
            vlan = port.vlan
            while vlan and canvas.stringWidth(vlan, "Helvetica", 5.5) > self.tile_w - 1 * mm:
                vlan = vlan[:-1]
            canvas.drawCentredString(x + self.tile_w / 2, y + 1.6 * mm, vlan)

        if disabled:
            # Small cross in the top right corner, away from the text.
            size, inset = 1.4 * mm, 0.7 * mm
            right, top = x + self.tile_w - inset, y + TILE_H - inset
            canvas.setStrokeColor(colors.HexColor("#dc3545"))
            canvas.setLineWidth(0.8)
            canvas.line(right - size, top - size, right, top)
            canvas.line(right - size, top, right, top - size)
        canvas.setLineWidth(0.5)


MIN_TILE_W = 8.5 * mm


def _layout(columns, optical, width):
    """(tile width, column chunks): shrink tiles to fit one row, wrap evenly only if still too wide."""
    preferred = OPTICAL_W if optical else TILE_W
    count = max(len(columns), 1)
    fitting = (width - TILE_GAP) / count - TILE_GAP
    if fitting >= MIN_TILE_W:
        return min(preferred, fitting), [columns]
    per_row = max(int((width - TILE_GAP) // (MIN_TILE_W + TILE_GAP)), 1)
    chunks = math.ceil(count / per_row)
    size = math.ceil(count / chunks)
    tile_w = min(preferred, (width - TILE_GAP) / size - TILE_GAP)
    return tile_w, [columns[index : index + size] for index in range(0, count, size)]


def _styles():
    sheet = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=sheet["Title"], alignment=0, fontSize=16, spaceAfter=1 * mm),
        "meta": ParagraphStyle("m", parent=sheet["Normal"], fontSize=8.5, textColor=colors.HexColor("#495057")),
        "h2": ParagraphStyle("h", parent=sheet["Heading2"], fontSize=11, spaceBefore=3 * mm, spaceAfter=1.5 * mm),
        "group": ParagraphStyle("g", parent=sheet["Normal"], fontSize=7.5, textColor=colors.HexColor("#495057")),
        "cell": ParagraphStyle("c", parent=sheet["Normal"], fontSize=6.5, leading=7.8),
        "figure": ParagraphStyle("f", parent=sheet["Normal"], fontSize=14, leading=16),
        "small": ParagraphStyle("s", parent=sheet["Normal"], fontSize=7, textColor=colors.HexColor("#495057")),
    }


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _key_figures(summary, t):
    cells = [
        (t["ports"], str(summary["total"]), colors.HexColor("#212529")),
        (t["connected"], f"{summary['connected']}  ({summary['percent']} %)", colors.HexColor("#198754")),
        (t["free"], str(summary["free"]), colors.HexColor("#212529")),
        (t["disabled"], str(summary["disabled"]), colors.HexColor("#6c757d")),
    ]
    data = [
        [
            Paragraph(f'<font size="7" color="#6c757d">{label.upper()}</font>', _styles()["cell"])
            for label, _, _ in cells
        ],
        [
            Paragraph(f'<font size="14" color="{hex_of(color)}"><b>{value}</b></font>', _styles()["figure"])
            for _, value, color in cells
        ],
    ]
    table = Table(data, colWidths=[(PAGE[0] - 2 * MARGIN) / 4] * 4, rowHeights=[5 * mm, 9 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 1), 0.5, BORDER_LIGHT),
                ("BOX", (1, 0), (1, 1), 0.5, BORDER_LIGHT),
                ("BOX", (2, 0), (2, 1), 0.5, BORDER_LIGHT),
                ("BOX", (3, 0), (3, 1), 0.5, BORDER_LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1 * mm),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def _legend(ports, t, styles):
    legend = switch_ports.vlan_legend(ports)
    items = []
    for vlan, color, total, connected in legend:
        fill = colors.HexColor(color) if color else UNLABELLED_FILL
        label = _escape(vlan) if vlan else t["no_label"]
        items.append((fill, f"{label}  <font color='#6c757d'>({connected}/{total})</font>"))
    if not items:
        return []
    per_row = 4
    cells = []
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 1 * mm)]
    for row_index in range(math.ceil(len(items) / per_row)):
        row = []
        for column_index, (fill, text) in enumerate(items[row_index * per_row : (row_index + 1) * per_row]):
            row.extend(["", Paragraph(text, styles["cell"])])
            style.append(("BACKGROUND", (column_index * 2, row_index), (column_index * 2, row_index), fill))
            style.append(("BOX", (column_index * 2, row_index), (column_index * 2, row_index), 0.4, BORDER_LIGHT))
        row.extend([""] * (per_row * 2 - len(row)))
        cells.append(row)
    widths = [4 * mm, (PAGE[0] - 2 * MARGIN) / per_row - 4 * mm] * per_row
    table = Table(cells, colWidths=widths, rowHeights=5 * mm)
    table.setStyle(TableStyle(style))
    return [Paragraph(f"<b>{t['legend_vlan']}</b>", styles["small"]), Spacer(0, 1 * mm), table]


def _port_table(ports, t, styles):
    header = [t["port"], t["status"], t["vlan"], t["peer"], t["description"], t["type"], t["lag"]]
    data = [[Paragraph(f"<b>{text}</b>", styles["cell"]) for text in header]]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dee2e6")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dee2e6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.8 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8 * mm),
    ]
    states = {
        switch_ports.STATE_CONNECTED: t["connected"],
        switch_ports.STATE_FREE: t["free"],
        switch_ports.STATE_DISABLED: t["disabled"],
    }
    for index, port in enumerate(ports, start=1):
        name = _escape(port.name) + (f" <font color='#0d6efd'>[{t['mgmt']}]</font>" if port.mgmt_only else "")
        peer = port.peer if port.peer != switch_ports.MARKED_CONNECTED else t["marked"]
        data.append(
            [
                Paragraph(name, styles["cell"]),
                Paragraph(states[port.state], styles["cell"]),
                Paragraph(_escape(port.label) or "–", styles["cell"]),
                Paragraph(_escape(peer) or "–", styles["cell"]),
                Paragraph(_escape(port.description) or "–", styles["cell"]),
                Paragraph(_escape(port.type_display), styles["cell"]),
                Paragraph(_escape(port.lag) or "–", styles["cell"]),
            ]
        )
        if port.color:
            fill = colors.HexColor(port.color)
            style.append(("BACKGROUND", (2, index), (2, index), fill))
            data[index][2] = Paragraph(
                f"<font color='{hex_of(text_color(fill))}'>{_escape(port.label)}</font>", styles["cell"]
            )
        if port.state == switch_ports.STATE_DISABLED:
            style.append(("TEXTCOLOR", (0, index), (1, index), colors.HexColor("#6c757d")))
    width = PAGE[0] - 2 * MARGIN
    widths = [w * width for w in (0.19, 0.09, 0.12, 0.21, 0.17, 0.15, 0.07)]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def build_pdf(device, ports, lang="de", generated=None):
    """Return the PDF as bytes. ``device`` is a DeviceInfo, ``ports`` a list of switch_ports.Port."""
    t = TEXTS[language(lang)]
    styles = _styles()
    generated = generated or datetime.now()
    buffer = io.BytesIO()
    width = PAGE[0] - 2 * MARGIN

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#6c757d"))
        canvas.drawString(MARGIN, 7 * mm, f"{t['title']} – {device.name}")
        canvas.drawRightString(PAGE[0] - MARGIN, 7 * mm, f"{t['page']} {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        buffer,
        pagesize=PAGE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"{t['title']} – {device.name}",
        author="NetBox Utilities",
    )
    meta = [
        f"{t['site']}: {_escape(device.site)}" if device.site else "",
        f"{t['rack']}: {_escape(device.rack)}" if device.rack else "",
        f"{t['model']}: {_escape(device.model)}" if device.model else "",
        *[_escape(item) for item in device.extra],
        f"{t['generated']}: {generated.strftime(t['date_format'])}",
    ]
    story = [
        Paragraph(f"{t['title']} – {_escape(device.name)}", styles["title"]),
        Paragraph("  ·  ".join(part for part in meta if part), styles["meta"]),
        Spacer(0, 3 * mm),
        _key_figures(switch_ports.summary(ports), t),
        Paragraph(t["front"], styles["h2"]),
    ]

    switch_ports.assign_vlan_colors(ports)
    groups = switch_ports.build_groups(ports)
    if not groups:
        story.append(Paragraph(t["none"], styles["meta"]))
    for group in groups:
        tile_w, chunks = _layout(group.columns, group.optical, width)
        panels = [PortPanel(chunk, group.optical, width, tile_w) for chunk in chunks]
        title = Paragraph(f"{_escape(group.title)} · {len(group.ports)} {t['ports']}", styles["group"])
        block = [title, Spacer(0, 0.8 * mm)]
        for panel in panels:
            block.extend([panel, Spacer(0, 1.2 * mm)])
        story.append(KeepTogether(block))
        story.append(Spacer(0, 1.5 * mm))

    story.append(Paragraph(t["legend_state"], styles["small"]))
    story.append(Spacer(0, 2 * mm))
    story.extend(_legend(ports, t, styles))
    story.append(CondPageBreak(40 * mm))
    story.append(Paragraph(t["list"], styles["h2"]))
    story.append(_port_table(ports, t, styles))

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
