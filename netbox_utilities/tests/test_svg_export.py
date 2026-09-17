from django.test import SimpleTestCase

from netbox_utilities.svg_export import strip_svg_hyperlinks


class StripSvgHyperlinksTest(SimpleTestCase):
    def test_unwraps_anchor_elements_keeping_children(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<a xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="/dcim/devices/1/">'
            '<rect width="10" height="10"/>'
            "</a>"
            "</svg>"
        )

        result = strip_svg_hyperlinks(svg)

        self.assertNotIn("<a ", result)
        self.assertNotIn("href", result)
        self.assertIn("<rect", result)

    def test_removes_href_on_non_image_non_anchor_elements(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<use xlink:href="#some-symbol" href="#some-symbol"/>'
            "</svg>"
        )

        result = strip_svg_hyperlinks(svg)

        self.assertNotIn("href", result)
        self.assertIn("<use", result)

    def test_leaves_image_href_untouched_without_a_loader(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<image xlink:href="/media/devicetype-images/example.png"/>'
            "</svg>"
        )

        result = strip_svg_hyperlinks(svg)

        self.assertIn("/media/devicetype-images/example.png", result)

    def test_replaces_image_href_with_data_uri_from_loader(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<image xlink:href="/media/devicetype-images/example.png"/>'
            "</svg>"
        )

        result = strip_svg_hyperlinks(svg, image_loader=lambda href: "data:image/png;base64,AAAA")

        self.assertIn("data:image/png;base64,AAAA", result)
        self.assertNotIn("/media/devicetype-images/example.png", result)

    def test_drops_image_href_when_loader_cannot_resolve_it(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<image xlink:href="/media/devicetype-images/missing.png"/>'
            "</svg>"
        )

        result = strip_svg_hyperlinks(svg, image_loader=lambda href: None)

        self.assertNotIn("href", result)
        self.assertIn("<image", result)

    def test_preserves_sibling_order_around_unwrapped_anchor(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect id="before"/>'
            '<a href="/dcim/devices/2/"><rect id="linked"/></a>'
            '<rect id="after"/>'
            "</svg>"
        )

        result = strip_svg_hyperlinks(svg)

        self.assertLess(result.index('id="before"'), result.index('id="linked"'))
        self.assertLess(result.index('id="linked"'), result.index('id="after"'))

    def test_leaves_svg_without_links_unchanged_in_content(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="5" height="5"/></svg>'

        result = strip_svg_hyperlinks(svg)

        self.assertIn("<rect", result)
        self.assertNotIn("href", result)
