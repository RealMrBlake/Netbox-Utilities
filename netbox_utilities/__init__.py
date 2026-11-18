from netbox.plugins import PluginConfig, get_plugin_config

__version__ = "0.29.1"


class NetBoxUtilitiesConfig(PluginConfig):
    name = "netbox_utilities"
    verbose_name = "NetBox Utilities"
    description = "Navigation, tenant utilities, connection VLANs, partial-width racks, disks, CPU & RAM, switch port export, client software overview and bulk operations"
    version = __version__
    author = "LKE"
    base_url = "utilities"
    min_version = "4.6.5"
    max_version = "4.7.99"
    default_settings = {
        "navigation_customization_enabled": True,
        "connection_vlans_enabled": True,
        "connection_tenant_filter_enabled": True,
        "reorder_rack_bulk_save_enabled": True,
        "topology_views_rack_width_enabled": True,
        "tenant_filter_enabled": True,
        "tenant_required": True,
        "offline_svg_export_enabled": True,
        "site_prefix_column_enabled": True,
        "disks_enabled": True,
        "disk_device_roles": ["Server", "NAS", "SAN", "MSA"],
        "disk_age_warning_years": 5,
        "disk_warranty_warning_days": 90,
        "hardware_enabled": True,
        "hardware_device_roles": ["Server"],
        "hardware_vcpu_ratio_warning": 4,
        "switch_ports_enabled": True,
        "switch_device_roles": ["Switch"],
        "wireless_trace_enabled": True,
        "software_enabled": True,
        "software_device_roles": ["Client", "Windows Client"],
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
        if get_plugin_config("netbox_utilities", "disks_enabled"):
            from .disk_integration import install_disk_support

            install_disk_support()
        if get_plugin_config("netbox_utilities", "hardware_enabled"):
            from .hardware_integration import install_hardware_support

            install_hardware_support()
        if get_plugin_config("netbox_utilities", "site_prefix_column_enabled"):
            from .site_prefix import install_site_prefix_column

            install_site_prefix_column()
        if get_plugin_config("netbox_utilities", "connection_vlans_enabled"):
            from .connection_vlans import install_connection_vlan_support

            install_connection_vlan_support()
        if get_plugin_config("netbox_utilities", "connection_tenant_filter_enabled"):
            from .connection_scope import install_connection_scope_filter

            install_connection_scope_filter()
        if get_plugin_config("netbox_utilities", "wireless_trace_enabled"):
            from .wireless_trace import install_wireless_trace

            install_wireless_trace()
        if self.apps.is_installed("netbox_export"):
            from .netbox_export import install_netbox_export_rack_width_support

            install_netbox_export_rack_width_support()
        if self.apps.is_installed("netbox_inventory"):
            from .inventory_assets import install_asset_tenant_column

            install_asset_tenant_column()
        if get_plugin_config("netbox_utilities", "software_enabled") and self.apps.is_installed("netbox_slm"):
            from .software_integration import install_software_support

            install_software_support()
        if get_plugin_config("netbox_utilities", "reorder_rack_bulk_save_enabled"):
            from .reorder_rack import install_reorder_rack_bulk_save

            install_reorder_rack_bulk_save()


config = NetBoxUtilitiesConfig
