from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from netbox_utilities.module_installation import (
    BulkModuleInstallError,
    build_module_form_data,
    install_modules,
)


class BulkModuleInstallationTest(SimpleTestCase):
    def setUp(self):
        self.device = SimpleNamespace(pk=10)
        self.module_type = SimpleNamespace(pk=20)
        self.module_bay = SimpleNamespace(pk=30, device_id=10, enabled=True, name="A1")

    def test_builds_core_module_form_data(self):
        data = build_module_form_data(
            self.device,
            self.module_bay,
            self.module_type,
            "active",
            True,
            "Patchmodul",
        )

        self.assertEqual(
            data,
            {
                "device": 10,
                "module_bay": 30,
                "module_type": 20,
                "status": "active",
                "replicate_components": True,
                "adopt_components": False,
                "description": "Patchmodul",
            },
        )

    @patch("netbox_utilities.module_installation.transaction.atomic")
    @patch("netbox_utilities.module_installation.ModuleForm")
    @patch("netbox_utilities.module_installation.ModuleBay")
    def test_installs_module_with_core_form(self, module_bay_model, module_form_class, atomic):
        module_bay_model.objects.select_for_update.return_value.filter.return_value = [self.module_bay]
        form = module_form_class.return_value
        form.is_valid.return_value = True
        installed_module = SimpleNamespace(pk=40)
        form.save.return_value = installed_module

        result = install_modules(
            device=self.device,
            module_type=self.module_type,
            module_bays=[self.module_bay],
            status="active",
            replicate_components=True,
            description="Patchmodul",
        )

        self.assertEqual(result, [installed_module])
        form.save.assert_called_once_with()
        atomic.assert_called_once_with()

    @patch("netbox_utilities.module_installation.transaction.atomic")
    @patch("netbox_utilities.module_installation.ModuleForm")
    @patch("netbox_utilities.module_installation.ModuleBay")
    def test_reports_bay_and_rolls_back_on_validation_error(self, module_bay_model, module_form_class, _atomic):
        module_bay_model.objects.select_for_update.return_value.filter.return_value = [self.module_bay]
        form = module_form_class.return_value
        form.is_valid.return_value = False
        form.errors = {"__all__": ["Eine Komponente existiert bereits."]}
        form.fields = {}

        with self.assertRaisesMessage(BulkModuleInstallError, 'Fehler bei Modulschacht "A1"'):
            install_modules(
                device=self.device,
                module_type=self.module_type,
                module_bays=[self.module_bay],
                status="active",
            )

        form.save.assert_not_called()

    @patch("netbox_utilities.module_installation.transaction.atomic")
    @patch("netbox_utilities.module_installation.ModuleForm")
    @patch("netbox_utilities.module_installation.ModuleBay")
    def test_rejects_module_outside_add_permission(self, module_bay_model, module_form_class, _atomic):
        module_bay_model.objects.select_for_update.return_value.filter.return_value = [self.module_bay]
        form = module_form_class.return_value
        form.is_valid.return_value = True
        form.save.return_value = SimpleNamespace(pk=40)
        permitted_modules = MagicMock()
        permitted_modules.filter.return_value.exists.return_value = False

        with self.assertRaisesMessage(BulkModuleInstallError, "Keine Berechtigung"):
            install_modules(
                device=self.device,
                module_type=self.module_type,
                module_bays=[self.module_bay],
                status="active",
                permitted_modules=permitted_modules,
            )
