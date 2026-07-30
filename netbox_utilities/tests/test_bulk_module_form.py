from types import SimpleNamespace

from django import forms
from django.forms.utils import ErrorDict
from django.test import SimpleTestCase

from netbox_utilities.forms import BulkModuleInstallForm


class AvailableModuleBays(list):
    def count(self):
        return len(self)


class BulkModuleInstallFormTest(SimpleTestCase):
    def _form_for_clean(self, *, module_bays=None, quantity=None, available_bays=None):
        form = BulkModuleInstallForm.__new__(BulkModuleInstallForm)
        forms.Form.__init__(form)
        form._errors = ErrorDict()
        form.cleaned_data = {
            "device": SimpleNamespace(pk=10),
            "module_bays": module_bays or [],
            "quantity": quantity,
        }
        form.available_module_bays = AvailableModuleBays(available_bays or [])
        return form

    def test_quantity_selects_first_available_bays(self):
        available_bays = [SimpleNamespace(pk=1), SimpleNamespace(pk=2), SimpleNamespace(pk=3)]
        form = self._form_for_clean(quantity=2, available_bays=available_bays)

        cleaned_data = form.clean()

        self.assertEqual(cleaned_data["module_bays"], available_bays[:2])
        self.assertFalse(form.errors)

    def test_quantity_cannot_exceed_available_bays(self):
        form = self._form_for_clean(quantity=3, available_bays=[SimpleNamespace(pk=1)])

        form.clean()

        self.assertIn("quantity", form.errors)
        self.assertIn("nur ein freier Modulschacht", str(form.errors["quantity"]))

    def test_quantity_and_manual_selection_are_mutually_exclusive(self):
        module_bay = SimpleNamespace(pk=1, name="A1", device_id=10, enabled=True)
        form = self._form_for_clean(module_bays=[module_bay], quantity=1, available_bays=[module_bay])

        form.clean()

        self.assertIn("quantity", form.errors)

    def test_requires_quantity_or_manual_selection(self):
        form = self._form_for_clean()

        form.clean()

        self.assertIn("__all__", form.errors)
