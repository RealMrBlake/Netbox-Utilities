"""Export device types as YAML in the community devicetype-library format.

The output can be re-imported through NetBox's own "Device Types > Import"
form or contributed to https://github.com/netbox-community/devicetype-library.
"""

import io
import zipfile

import yaml
from django.apps import apps
from django.utils.text import slugify

# (YAML key, related manager on DeviceType, fields exported per component)
COMPONENTS = [
    ("console-ports", "consoleporttemplates", ["type"]),
    ("console-server-ports", "consoleserverporttemplates", ["type"]),
    ("power-ports", "powerporttemplates", ["type", "maximum_draw", "allocated_draw"]),
    ("power-outlets", "poweroutlettemplates", ["type", "power_port", "feed_leg"]),
    ("interfaces", "interfacetemplates", ["type", "mgmt_only", "poe_mode", "poe_type"]),
    ("rear-ports", "rearporttemplates", ["type", "color", "positions"]),
    ("front-ports", "frontporttemplates", ["type", "color", "positions"]),
    ("module-bays", "modulebaytemplates", ["position"]),
    ("device-bays", "devicebaytemplates", []),
    ("inventory-items", "inventoryitemtemplates", ["manufacturer", "part_id"]),
]

DEVICE_TYPE_FIELDS = [
    "part_number",
    "u_height",
    "exclude_from_utilization",
    "is_full_depth",
    "subdevice_role",
    "airflow",
    "weight",
    "weight_unit",
    "description",
    "comments",
]

# Values that equal NetBox's defaults are dropped to keep the files short.
DEFAULTS = {
    "exclude_from_utilization": False,
    "mgmt_only": False,
    "positions": 1,
    "color": "",
}


def _plain(value):
    if value is None or value == "":
        return None
    if hasattr(value, "is_finite"):  # Decimal
        return int(value) if value == value.to_integral_value() else float(value)
    if hasattr(value, "_meta"):  # FK (power_port, manufacturer)
        return getattr(value, "name", str(value))
    return value


def _put(target, key, value):
    value = _plain(value)
    if value is None or DEFAULTS.get(key, object()) == value:
        return
    target[key] = value


def _front_port_mappings(device_type):
    """{front_port_id: (rear_port_name, rear_port_position)} for single mappings (NetBox >= 4.5)."""
    try:
        model = apps.get_model("dcim", "PortTemplateMapping")
    except LookupError:
        return {}
    mappings = {}
    for mapping in model.objects.filter(device_type=device_type).select_related("rear_port"):
        mappings.setdefault(mapping.front_port_id, []).append(mapping)
    return {
        front_id: (items[0].rear_port.name, items[0].rear_port_position)
        for front_id, items in mappings.items()
        if len(items) == 1
    }


def device_type_to_dict(device_type):
    data = {
        "manufacturer": device_type.manufacturer.name,
        "model": device_type.model,
        "slug": device_type.slug,
    }
    for field in DEVICE_TYPE_FIELDS:
        _put(data, field, getattr(device_type, field, None))

    mappings = None
    for key, manager, fields in COMPONENTS:
        items = []
        for component in getattr(device_type, manager).all():
            item = {"name": component.name}
            label = getattr(component, "label", "")
            if label:
                item["label"] = label
            for field in fields:
                if hasattr(component, field):
                    _put(item, field, getattr(component, field))
            if key == "front-ports":
                if mappings is None:
                    mappings = _front_port_mappings(device_type)
                legacy_rear = getattr(component, "rear_port", None)
                if component.pk in mappings:
                    item["rear_port"], item["rear_port_position"] = mappings[component.pk]
                elif legacy_rear is not None:  # NetBox < 4.5
                    item["rear_port"] = legacy_rear.name
                    item["rear_port_position"] = component.rear_port_position
            if component.description:
                item["description"] = component.description
            items.append(item)
        if items:
            data[key] = items
    return data


def device_type_to_yaml(device_type):
    return yaml.safe_dump(
        device_type_to_dict(device_type),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def filename(device_type):
    return f"{device_type.slug or slugify(device_type.model)}.yaml"


def device_types_to_zip(device_types):
    """ZIP laid out like the devicetype-library: <Manufacturer>/<slug>.yaml"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for device_type in device_types:
            archive.writestr(
                f"{device_type.manufacturer.name}/{filename(device_type)}",
                device_type_to_yaml(device_type),
            )
    return buffer.getvalue()
