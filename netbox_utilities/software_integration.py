"""Hooks the client software overview into NetBox: device tab and "Software" group in the Inventory menu."""

from django.core.signals import request_started

SOFTWARE_GROUP_LABEL = "Software"
INVENTORY_MENU_LABEL = "Inventory"
FALLBACK_MENU_LABEL = "Hardware"


def software_menu_items():
    from netbox.plugins import PluginMenuButton, PluginMenuItem

    return (
        PluginMenuItem(
            link="plugins:netbox_utilities:software_overview",
            link_text="Client Software Übersicht",
            permissions=["netbox_slm.view_softwareproductinstallation"],
            buttons=(
                PluginMenuButton(
                    link="plugins:netbox_slm:softwareproductinstallation_add",
                    title="Installation erfassen",
                    icon_class="mdi mdi-plus-thick",
                    permissions=["netbox_slm.add_softwareproductinstallation"],
                ),
            ),
        ),
    )


def add_software_group(menus):
    """
    Append the "Software" group to the Inventory menu of netbox-inventory.

    Falls back to the plugin's own "Hardware" menu if netbox-inventory has no top-level menu.
    Returns the menu that received the group, or None.
    """
    from netbox.navigation import MenuGroup

    menus = list(menus)
    target = next((menu for menu in menus if str(menu.label) == INVENTORY_MENU_LABEL), None)
    target = target or next((menu for menu in menus if str(menu.label) == FALLBACK_MENU_LABEL), None)
    if target is None:
        return None
    groups = list(target.groups)
    if any(str(group.label) == SOFTWARE_GROUP_LABEL for group in groups):
        return target
    groups.append(MenuGroup(SOFTWARE_GROUP_LABEL, software_menu_items()))
    target.groups = groups
    return target


def _install_menu_on_first_request(**kwargs):
    # All plugins have registered their menus once the first request arrives.
    request_started.disconnect(dispatch_uid=__name__)
    from netbox.registry import registry

    add_software_group(registry["plugins"]["menus"])


def install_software_support():
    # Registers the device "Software" tab before NetBox builds the dcim URLs.
    from . import software_views  # noqa: F401
    from .software_sync import install_software_sync

    # Software lists of the Windows agent and the NetBox Synchronizer arrive in the device comments.
    install_software_sync()

    request_started.connect(_install_menu_on_first_request, dispatch_uid=__name__)
