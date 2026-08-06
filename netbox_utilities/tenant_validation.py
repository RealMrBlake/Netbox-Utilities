from functools import wraps

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db.models.signals import pre_save
from django.forms.models import BaseModelForm
from tenancy.models import Tenant

from .runtime import tenant_required
from .tenant_autofill import apply_cable_instance_tenant, apply_tenant_autofill

VALIDATION_MESSAGE = "Für dieses Objekt muss ein Mandant angegeben werden."


def model_supports_tenant(model):
    try:
        field = model._meta.get_field("tenant")
    except FieldDoesNotExist:
        return False
    return field.concrete and field.is_relation and field.related_model is Tenant


def validate_tenant_assignment(instance):
    if tenant_required() and model_supports_tenant(type(instance)) and getattr(instance, "tenant_id", None) is None:
        # A non-field error is intentional: a small number of specialized
        # ModelForms omit the tenant field and Django cannot attach errors to
        # fields which are absent from a form.
        raise ValidationError(VALIDATION_MESSAGE)


def _install_model_clean_validation(model):
    if not model_supports_tenant(model) or getattr(model, "_netbox_utilities_tenant_validation", False):
        return

    original_clean = model.clean

    @wraps(original_clean)
    def tenant_aware_clean(instance, *args, **kwargs):
        apply_cable_instance_tenant(instance)
        result = original_clean(instance, *args, **kwargs)
        validate_tenant_assignment(instance)
        return result

    model.clean = tenant_aware_clean
    model._netbox_utilities_tenant_validation = True


def _install_form_validation():
    if getattr(BaseModelForm, "_netbox_utilities_tenant_validation", False):
        return

    original_init = BaseModelForm.__init__

    @wraps(original_init)
    def tenant_aware_init(form, *args, **kwargs):
        original_init(form, *args, **kwargs)
        model = getattr(form._meta, "model", None)
        if tenant_required() and model and model_supports_tenant(model) and "tenant" in form.fields:
            form.fields["tenant"].required = True
        apply_tenant_autofill(form)

    BaseModelForm.__init__ = tenant_aware_init
    BaseModelForm._netbox_utilities_tenant_validation = True


def _enforce_before_save(sender, instance, raw=False, **kwargs):
    if not raw:
        validate_tenant_assignment(instance)


def install_tenant_validation():
    for model in apps.get_models():
        _install_model_clean_validation(model)
    _install_form_validation()
    pre_save.connect(
        _enforce_before_save,
        dispatch_uid="netbox_utilities.enforce_tenant_before_save",
        weak=False,
    )
