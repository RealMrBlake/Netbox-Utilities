import re

from django.db import migrations


def natural_port_key(port):
    parts = tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", str(port.name))
    )
    return parts, port.pk


def synchronize_existing_patchpanels(apps, schema_editor):
    Device = apps.get_model("dcim", "Device")
    FrontPort = apps.get_model("dcim", "FrontPort")
    PortMapping = apps.get_model("dcim", "PortMapping")
    RearPort = apps.get_model("dcim", "RearPort")
    database = schema_editor.connection.alias

    device_ids = Device.objects.using(database).filter(role__name__iexact="Patchpanel").values_list("pk", flat=True)
    for device_id in device_ids.iterator():
        front_ports = sorted(
            FrontPort.objects.using(database).filter(device_id=device_id).only("pk", "name"),
            key=natural_port_key,
        )
        rear_ports = sorted(
            RearPort.objects.using(database).filter(device_id=device_id).only("pk", "name"),
            key=natural_port_key,
        )
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
                for front_port, rear_port in zip(front_ports, rear_ports)
            ],
            batch_size=1000,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0237_module_remove_local_context_data"),
        ("netbox_utilities", "0003_navigationpreference_sidebar_layout"),
    ]

    operations = [
        migrations.RunPython(synchronize_existing_patchpanels, migrations.RunPython.noop),
    ]
