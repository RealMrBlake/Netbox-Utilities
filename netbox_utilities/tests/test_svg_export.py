from django.test import SimpleTestCase

from netbox_utilities.svg_export import apply_rack_view_mode, strip_svg_hyperlinks


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


class ApplyRackViewModeTest(SimpleTestCase):
    SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<text class="label">USV 8</text>'
        '<image class="device-image"/>'
        '<text class="device-image-label">USV 8</text>'
        "</svg>"
    )

    def test_images_and_labels_leaves_svg_untouched(self):
        self.assertEqual(apply_rack_view_mode(self.SVG, "images-and-labels"), self.SVG)

    def test_images_only_keeps_only_the_image(self):
        result = apply_rack_view_mode(self.SVG, "images-only")

        self.assertNotIn('class="label"', result)
        self.assertNotIn("device-image-label", result)
        self.assertIn('class="device-image"', result)

    def test_labels_only_keeps_only_the_plain_label(self):
        result = apply_rack_view_mode(self.SVG, "labels-only")

        self.assertIn('class="label"', result)
        self.assertNotIn("device-image", result)

    def test_unknown_mode_leaves_svg_untouched(self):
        self.assertEqual(apply_rack_view_mode(self.SVG, "bogus"), self.SVG)
