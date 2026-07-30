from dcim.forms import ModuleForm
from dcim.models import ModuleBay
from django.db import IntegrityError, transaction


class BulkModuleInstallError(Exception):
    pass


def build_module_form_data(device, module_bay, module_type, status, replicate_components, description=""):
    return {
        "device": device.pk,
        "module_bay": module_bay.pk,
        "module_type": module_type.pk,
        "status": status,
        "replicate_components": replicate_components,
        "adopt_components": False,
        "description": description,
    }


def _format_form_errors(form):
    messages = []
    for field_name, errors in form.errors.items():
        field = form.fields.get(field_name)
        label = field.label if field else "Allgemeiner Fehler"
        messages.append(f"{label}: {', '.join(str(error) for error in errors)}")
    return "; ".join(messages)


def install_modules(
    *,
    device,
    module_type,
    module_bays,
    status,
    replicate_components=True,
    description="",
    permitted_modules=None,
):
    module_bay_ids = {module_bay.pk for module_bay in module_bays}
    if not module_bay_ids:
        return []

    try:
        with transaction.atomic():
            locked_bays = list(ModuleBay.objects.select_for_update().filter(pk__in=module_bay_ids))
            if {module_bay.pk for module_bay in locked_bays} != module_bay_ids:
                raise BulkModuleInstallError("Mindestens ein ausgewählter Modulschacht existiert nicht mehr.")

            installed_modules = []
            for module_bay in locked_bays:
                if (
                    module_bay.device_id != device.pk
                    or not module_bay.enabled
                    or hasattr(module_bay, "installed_module")
                ):
                    raise BulkModuleInstallError(f'Der Modulschacht "{module_bay.name}" ist nicht mehr verfügbar.')

                module_form = ModuleForm(
                    data=build_module_form_data(
                        device,
                        module_bay,
                        module_type,
                        status,
                        replicate_components,
                        description,
                    )
                )
                if not module_form.is_valid():
                    raise BulkModuleInstallError(
                        f'Fehler bei Modulschacht "{module_bay.name}": {_format_form_errors(module_form)}'
                    )
                module = module_form.save()
                if permitted_modules is not None and not permitted_modules.filter(pk=module.pk).exists():
                    raise BulkModuleInstallError(
                        f'Keine Berechtigung zum Einbau eines Moduls in Modulschacht "{module_bay.name}".'
                    )
                installed_modules.append(module)

            return installed_modules
    except IntegrityError as error:
        raise BulkModuleInstallError(
            "Der Masseneinbau konnte wegen eines zwischenzeitlichen Datenkonflikts nicht gespeichert werden."
        ) from error
