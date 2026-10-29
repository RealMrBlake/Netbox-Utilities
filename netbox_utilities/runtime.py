from django.core.cache import cache
from django.db import OperationalError, ProgrammingError, transaction
from netbox.plugins import get_plugin_config

from .models import UtilitiesSettings

SETTINGS_CACHE_KEY = "netbox_utilities.runtime_settings.v2"


def navigation_customization_enabled():
    return bool(get_plugin_config("netbox_utilities", "navigation_customization_enabled"))


def connection_vlans_enabled():
    return bool(get_plugin_config("netbox_utilities", "connection_vlans_enabled"))


def hardware_enabled():
    return bool(get_plugin_config("netbox_utilities", "hardware_enabled"))


def offline_svg_export_enabled():
    return bool(get_plugin_config("netbox_utilities", "offline_svg_export_enabled"))


def tenant_filter_enabled():
    if not get_plugin_config("netbox_utilities", "tenant_filter_enabled"):
        return False

    return bool(_get_database_settings()["tenant_filter_enabled"])


def tenant_required():
    if not get_plugin_config("netbox_utilities", "tenant_required"):
        return False

    return bool(_get_database_settings()["tenant_required"])


def _get_database_settings():
    runtime_settings = cache.get(SETTINGS_CACHE_KEY)
    if runtime_settings is None:
        try:
            # The savepoint keeps an outer transaction (e.g. a running migration)
            # usable on PostgreSQL if the settings table does not exist yet.
            with transaction.atomic():
                runtime_settings = (
                    UtilitiesSettings.objects.filter(singleton_id=1)
                    .values("tenant_filter_enabled", "tenant_required")
                    .first()
                )
        except (OperationalError, ProgrammingError):
            # The middleware can be imported before the first plugin migration.
            runtime_settings = None
        runtime_settings = runtime_settings or {
            "tenant_filter_enabled": True,
            "tenant_required": True,
        }
        cache.set(SETTINGS_CACHE_KEY, runtime_settings, timeout=30)
    return runtime_settings


def clear_runtime_settings_cache():
    cache.delete(SETTINGS_CACHE_KEY)
