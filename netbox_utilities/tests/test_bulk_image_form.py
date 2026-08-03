from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils.datastructures import MultiValueDict
from PIL import Image

from netbox_utilities.forms import BulkImageUploadForm


class BulkImageUploadFormTest(SimpleTestCase):
    @staticmethod
    def _image(name):
        content = BytesIO()
        Image.new("RGB", (2, 2), "white").save(content, format="PNG")
        return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")

    def test_accepts_multiple_images(self):
        files = MultiValueDict({"images": [self._image("front.png"), self._image("rear.png")]})

        form = BulkImageUploadForm(data={"description": "Dokumentation"}, files=files)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.cleaned_data["images"]), 2)
        self.assertEqual(form.cleaned_data["description"], "Dokumentation")

    def test_requires_at_least_one_image(self):
        form = BulkImageUploadForm(data={}, files={})

        self.assertFalse(form.is_valid())
        self.assertIn("images", form.errors)
