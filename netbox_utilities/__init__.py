from netbox.plugins import PluginConfig, get_plugin_config

__version__ = "0.12.2"


class NetBoxUtilitiesConfig(PluginConfig):
    name = "netbox_utilities"
    verbose_name = "NetBox Utilities"
    description = "Navigation, tenant utilities, connection VLANs, partial-width racks, and bulk operations"
    version = __version__
    author = "LKE"
    base_url = "utilities"
    min_version = "4.6.5"
    max_version = "4.7.99"
    default_settings = {
        "navigation_customization_enabled": True,
        "connection_vlans_enabled": True,
        "reorder_rack_bulk_save_enabled": True,
        "topology_views_rack_width_enabled": True,
        "tenant_filter_enabled": True,
        "tenant_required": True,
        "offline_svg_export_enabled": True,
    }
    middleware = [
        "netbox_utilities.middleware.GlobalTenantFilterMiddleware",
    ]

    def ready(self):
        super().ready()
        from .patchpanel import install_patchpanel_automation
        from .rack_width import install_rack_width_support
        from .tenant_scope import install_search_filter
        from .tenant_validation import install_tenant_validation

        install_search_filter()
        install_tenant_validation()
        install_patchpanel_automation()
        install_rack_width_support()
        if get_plugin_config("netbox_utilities", "connection_vlans_enabled"):
            from .connection_vlans import install_connection_vlan_support

            install_connection_vlan_support()
        if self.apps.is_installed("netbox_export"):
            from .netbox_export import install_netbox_export_rack_width_support

            install_netbox_export_rack_width_support()
        if get_plugin_config("netbox_utilities", "reorder_rack_bulk_save_enabled"):
            from .reorder_rack import install_reorder_rack_bulk_save

            install_reorder_rack_bulk_save()


config = NetBoxUtilitiesConfig
