from django.conf import settings
from django.contrib.auth.context_processors import PermWrapper
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from netbox_utilities.template_content import UtilitiesGlobalContent


class OptionalRackIntegrationHeadTest(SimpleTestCase):
    def test_foreign_rack_adapters_are_not_loaded_by_the_global_head(self):
        request = RequestFactory().get("/dcim/racks/3/reorder/")
        request.user = AnonymousUser()
        html = UtilitiesGlobalContent(
            {
                "request": request,
                "settings": settings,
                "csrf_token": "",
                "perms": PermWrapper(request.user),
            }
        ).head()

        self.assertNotIn("netbox-utilities-reorder-rack-width-data", html)
        self.assertNotIn("netbox-utilities-topology-rack-width-data", html)
