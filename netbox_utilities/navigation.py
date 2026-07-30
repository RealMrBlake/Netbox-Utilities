from netbox.plugins import PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_utilities:bulk_module_install",
        link_text="Module mehrfach einbauen",
        auth_required=True,
        permissions=("dcim.add_module",),
    ),
    PluginMenuItem(
        link="plugins:netbox_utilities:navigation_preferences",
        link_text="Navigation personalisieren",
        auth_required=True,
    ),
    PluginMenuItem(
        link="plugins:netbox_utilities:settings",
        link_text="Einstellungen",
        staff_only=True,
    ),
)
