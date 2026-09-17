import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

_ANCHOR_TAGS = (f"{{{SVG_NS}}}a", "a")
_HREF_ATTRS = ("href", f"{{{XLINK_NS}}}href")


def strip_svg_hyperlinks(svg_source):
    """Return svg_source with every <a> wrapper unwrapped and href/xlink:href removed.

    NetBox wraps rack elevation devices in hyperlinks pointing at internal,
    relative object URLs. Those links are dead weight (and broken paths) once
    the SVG is saved and opened outside of a NetBox session, so this produces
    a self-contained file with the same visuals but no link markup.
    """
    root = ET.fromstring(svg_source)
    _unwrap_anchors(root)
    _strip_href_attributes(root)
    return ET.tostring(root, encoding="unicode")


def _unwrap_anchors(parent):
    replaced = False
    new_children = []
    for child in list(parent):
        _unwrap_anchors(child)
        if child.tag in _ANCHOR_TAGS:
            replaced = True
            new_children.extend(list(child))
        else:
            new_children.append(child)
    if replaced:
        for child in list(parent):
            parent.remove(child)
        for child in new_children:
            parent.append(child)


def _strip_href_attributes(element):
    for attr in _HREF_ATTRS:
        element.attrib.pop(attr, None)
    for child in element:
        _strip_href_attributes(child)
