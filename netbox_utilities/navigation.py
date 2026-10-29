from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

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

# Own top-level menu for server hardware; the disk entry opens the list grouped by device.
menu = PluginMenu(
    label="Hardware",
    icon_class="mdi mdi-server",
    groups=(
        (
            "Datenträger",
            (
                PluginMenuItem(
                    link="plugins:netbox_utilities:disk_by_device",
                    link_text="Datenträger",
                    permissions=("netbox_utilities.view_disk",),
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_utilities:disk_bulk_import",
                            title="Importieren",
                            icon_class="mdi mdi-upload",
                            permissions=("netbox_utilities.add_disk",),
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_utilities:disk_msa_import",
                            title="HPE-MSA-Export importieren",
                            icon_class="mdi mdi-database-import",
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
            ),
        ),
        (
            "CPU & RAM",
            (
                PluginMenuItem(
                    link="plugins:netbox_utilities:devicehardware_list",
                    link_text="CPU & RAM",
                    permissions=("netbox_utilities.view_devicehardware",),
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_utilities:devicehardware_add",
                            title="Hinzufügen",
                            icon_class="mdi mdi-plus-thick",
                            permissions=("netbox_utilities.add_devicehardware",),
                        ),
                        PluginMenuButton(
                            link="plugins:netbox_utilities:devicehardware_bulk_import",
                            title="Importieren",
                            icon_class="mdi mdi-upload",
                            permissions=("netbox_utilities.add_devicehardware",),
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_utilities:cpumodel_list",
                    link_text="CPU-Modelle",
                    permissions=("netbox_utilities.view_cpumodel",),
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_utilities:cpumodel_add",
                            title="Hinzufügen",
                            icon_class="mdi mdi-plus-thick",
                            permissions=("netbox_utilities.add_cpumodel",),
                        ),
                    ),
                ),
            ),
        ),
    ),
)
