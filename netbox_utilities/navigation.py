from netbox.plugins import PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_utilities:disk_list",
        link_text="Datenträger",
        permissions=("netbox_utilities.view_disk",),
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_utilities:disk_bulk_import",
                title="Importieren",
                icon_class="mdi mdi-upload",
                permissions=("netbox_utilities.add_disk",),
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:netbox_utilities:raidgroup_list",
        link_text="RAID-Gruppen",
        permissions=("netbox_utilities.view_raidgroup",),
    ),
    PluginMenuItem(
        link="plugins:netbox_utilities:diskbaytemplate_list",
        link_text="Datenträger-Vorlagen",
        permissions=("netbox_utilities.view_diskbaytemplate",),
    ),
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
