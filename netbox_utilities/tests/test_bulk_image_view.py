from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from netbox_utilities.views import BulkImageUploadView


class BulkImageUploadViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.parent = SimpleNamespace(get_absolute_url=lambda: "/dcim/sites/42/")

    def test_accepts_local_return_url(self):
        request = self.factory.get("/plugins/utilities/images/bulk-upload/?return_url=/dcim/sites/42/images/")

        result = BulkImageUploadView()._return_url(request, self.parent)

        self.assertEqual(result, "/dcim/sites/42/images/")

    def test_rejects_external_return_url(self):
        request = self.factory.get("/plugins/utilities/images/bulk-upload/?return_url=https://example.net/steal")

        result = BulkImageUploadView()._return_url(request, self.parent)

        self.assertEqual(result, "/dcim/sites/42/")
