from netbox.navigation.menu import get_menus


def _permitted_menu_items(menu, user):
    for group in menu.groups:
        for item in group.items:
            if getattr(item, "auth_required", False) and not user.is_authenticated:
                continue
            if item.staff_only and not user.is_superuser:
                continue
            if not user.has_perms(item.permissions):
                continue
            yield item


def get_visible_menus(user):
    """Return stable descriptors for every sidebar menu visible to the user."""
    descriptors = []
    used_keys = set()

    for index, menu in enumerate(get_menus()):
        items = list(_permitted_menu_items(menu, user))
        if not items:
            continue

        first_url = str(items[0].url)
        key = first_url or menu.icon_class or f"menu-{index}"
        if key in used_keys:
            key = f"{key}#{index}"
        used_keys.add(key)
        descriptors.append(
            {
                "key": key,
                "label": str(menu.label),
                "icon_class": menu.icon_class,
                "first_url": first_url,
            }
        )

    return descriptors


def normalize_preferences(menu_order, hidden_menus, available_keys):
    """Discard forged/stale keys and append newly introduced menus."""
    allowed = list(dict.fromkeys(available_keys))
    allowed_set = set(allowed)
    order = [key for key in dict.fromkeys(menu_order) if key in allowed_set]
    order.extend(key for key in allowed if key not in order)
    hidden = [key for key in dict.fromkeys(hidden_menus) if key in allowed_set]
    return order, hidden
