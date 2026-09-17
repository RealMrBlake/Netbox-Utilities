import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

_ANCHOR_TAGS = (f"{{{SVG_NS}}}a", "a")
_IMAGE_TAGS = (f"{{{SVG_NS}}}image", "image")
_HREF_ATTRS = ("href", f"{{{XLINK_NS}}}href")

RACK_VIEW_MODES = {"images-and-labels", "images-only", "labels-only"}
_PLAIN_LABEL_CLASS = "label"
_IMAGE_CLASS = "device-image"
_IMAGE_LABEL_CLASS = "device-image-label"


def apply_rack_view_mode(svg_source, mode):
    """Filter the rack elevation SVG down to images-only or labels-only content.

    NetBox's own "Bilder"/"Beschriftungen" toggle never actually removes the
    plain .label text: it just leaves an opaque .device-image sitting on top
    of it, so a device without a photo still shows its name in "images-only"
    live. A downloaded, static export has no such fallback text to hide
    behind an image, so here "images-only" removes every label outright
    (.label and .device-image-label) to always produce a pure image view,
    and "labels-only" removes the image layer to reproduce the same
    box-with-text view NetBox itself already shows for that mode.
    """
    if mode not in RACK_VIEW_MODES or mode == "images-and-labels":
        return svg_source
    root = ET.fromstring(svg_source)
    if mode == "images-only":
        _remove_elements_with_class(root, {_PLAIN_LABEL_CLASS, _IMAGE_LABEL_CLASS})
    elif mode == "labels-only":
        _remove_elements_with_class(root, {_IMAGE_CLASS, _IMAGE_LABEL_CLASS})
    return ET.tostring(root, encoding="unicode")


def _remove_elements_with_class(parent, class_names):
    for child in list(parent):
        classes = set(child.attrib.get("class", "").split())
        if classes & class_names:
            parent.remove(child)
        else:
            _remove_elements_with_class(child, class_names)


def strip_svg_hyperlinks(svg_source, image_loader=None):
    """Return svg_source with every <a> wrapper unwrapped and dead links removed.

    NetBox wraps rack elevation devices in hyperlinks pointing at internal,
    relative object URLs. Those links are dead weight (and broken paths) once
    the SVG is saved and opened outside of a NetBox session, so this unwraps
    them while keeping their contents.

    <image> elements reference device photos by the same kind of internal,
    relative URL. Simply stripping their href would leave the device blank,
    so image_loader (href -> "data:...;base64,..." or None) is used to embed
    the image data directly instead. Without an image_loader, image hrefs are
    left untouched.
    """
    root = ET.fromstring(svg_source)
    _unwrap_anchors(root)
    _resolve_hrefs(root, image_loader)
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


def _resolve_hrefs(element, image_loader):
    if element.tag in _IMAGE_TAGS:
        if image_loader is not None:
            for attr in _HREF_ATTRS:
                href = element.attrib.get(attr)
                if not href:
                    continue
                data_uri = image_loader(href)
                if data_uri:
                    element.attrib[attr] = data_uri
                else:
                    element.attrib.pop(attr, None)
    else:
        for attr in _HREF_ATTRS:
            element.attrib.pop(attr, None)
    for child in element:
        _resolve_hrefs(child, image_loader)
