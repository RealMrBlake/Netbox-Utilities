import re
from collections import defaultdict

from django.db import migrations


def natural_port_key(port):
    parts = tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", str(port.name))
    )
    return parts, port.pk


def port_identifier(port):
    name = str(port.name).casefold()
    name = re.sub(r"\b(?:front|rear)(?:[\s_-]*port)?(?=\b|\d)", " ", name)
    name = re.sub(r"^(?:fp|rp|f|r)(?=\s*[-_.:/]?\s*\d)", "", name)
    tokens = re.findall(r"\d+|[^\W\d_]+", name)
    identifier = tuple(int(token) if token.isdigit() else token for token in tokens)
    return identifier or None


def pair_ports(front_ports, rear_ports):
    front_by_identifier = defaultdict(list)
    rear_by_identifier = defaultdict(list)
    for port in front_ports:
        if identifier := port_identifier(port):
            front_by_identifier[identifier].append(port)
    for port in rear_ports:
        if identifier := port_identifier(port):
            rear_by_identifier[identifier].append(port)

    pairs = []
    for identifier, matching_front_ports in front_by_identifier.items():
        pairs.extend(
            zip(
                sorted(matching_front_ports, key=natural_port_key),
                sorted(rear_by_identifier.get(identifier, []), key=natural_port_key),
            )
        )
    return pairs


def fix_existing_patchpanel_mappings(apps, schema_editor):
    Device = apps.get_model("dcim", "Device")
    FrontPort = apps.get_model("dcim", "FrontPort")
    PortMapping = apps.get_model("dcim", "PortMapping")
    RearPort = apps.get_model("dcim", "RearPort")
    database = schema_editor.connection.alias

    device_ids = Device.objects.using(database).filter(role__name__iexact="Patchpanel").values_list("pk", flat=True)
    for device_id in device_ids.iterator():
        front_ports = FrontPort.objects.using(database).filter(device_id=device_id).only("pk", "name")
        rear_ports = RearPort.objects.using(database).filter(device_id=device_id).only("pk", "name")
        pairs = pair_ports(front_ports, rear_ports)

        PortMapping.objects.using(database).filter(device_id=device_id).delete()
        PortMapping.objects.using(database).bulk_create(
            [
                PortMapping(
                    device_id=device_id,
                    front_port_id=front_port.pk,
                    rear_port_id=rear_port.pk,
                    front_port_position=1,
                    rear_port_position=1,
                )
                for front_port, rear_port in pairs
            ],
            batch_size=1000,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_utilities", "0004_patchpanel_port_mappings"),
    ]

    operations = [
        migrations.RunPython(fix_existing_patchpanel_mappings, migrations.RunPython.noop),
    ]
