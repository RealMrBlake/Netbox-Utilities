from django.core.cache import cache
from django.db import OperationalError, ProgrammingError
from netbox.plugins import get_plugin_config

from .models import UtilitiesSettings

SETTINGS_CACHE_KEY = "netbox_utilities.runtime_settings.v1"


def navigation_customization_enabled():
    return bool(get_plugin_config("netbox_utilities", "navigation_customization_enabled"))


def tenant_filter_enabled():
    if not get_plugin_config("netbox_utilities", "tenant_filter_enabled"):
        return False

    enabled = cache.get(SETTINGS_CACHE_KEY)
    if enabled is None:
        try:
            enabled = (
                UtilitiesSettings.objects.filter(singleton_id=1).values_list("tenant_filter_enabled", flat=True).first()
            )
        except (OperationalError, ProgrammingError):
            # The middleware can be imported before the first plugin migration.
            enabled = True
        enabled = True if enabled is None else enabled
        cache.set(SETTINGS_CACHE_KEY, enabled, timeout=30)
    return bool(enabled)


def clear_runtime_settings_cache():
    cache.delete(SETTINGS_CACHE_KEY)
