from netbox.plugins import PluginConfig, get_plugin_config

__version__ = "0.7.3"


class NetBoxUtilitiesConfig(PluginConfig):
    name = "netbox_utilities"
    verbose_name = "NetBox Utilities"
    description = "Navigation, tenant utilities, patchpanel mapping, bulk uploads, and atomic rack reordering"
    version = __version__
    author = "LKE"
    base_url = "utilities"
    min_version = "4.6.5"
    max_version = "4.6.99"
    default_settings = {
        "navigation_customization_enabled": True,
        "reorder_rack_bulk_save_enabled": True,
        "tenant_filter_enabled": True,
        "tenant_required": True,
    }
    middleware = [
        "netbox_utilities.middleware.GlobalTenantFilterMiddleware",
    ]

    def ready(self):
        super().ready()
        from .patchpanel import install_patchpanel_automation
        from .tenant_scope import install_search_filter
        from .tenant_validation import install_tenant_validation

        install_search_filter()
        install_tenant_validation()
        install_patchpanel_automation()
        if get_plugin_config("netbox_utilities", "reorder_rack_bulk_save_enabled"):
            from .reorder_rack import install_reorder_rack_bulk_save

            install_reorder_rack_bulk_save()


config = NetBoxUtilitiesConfig
