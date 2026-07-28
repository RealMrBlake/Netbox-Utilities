from netbox.plugins import PluginConfig


class NetBoxUtilitiesConfig(PluginConfig):
    name = "netbox_utilities"
    verbose_name = "NetBox Utilities"
    description = "Personal navigation and a global tenant filter"
    version = "0.1.0"
    author = "LKE"
    base_url = "utilities"
    min_version = "4.6.5"
    max_version = "4.6.99"
    default_settings = {
        "navigation_customization_enabled": True,
        "tenant_filter_enabled": True,
    }
    middleware = [
        "netbox_utilities.middleware.GlobalTenantFilterMiddleware",
    ]

    def ready(self):
        super().ready()
        from .tenant_scope import install_search_filter

        install_search_filter()


config = NetBoxUtilitiesConfig
