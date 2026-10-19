import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def assign_disks_to_existing_layouts(apps, schema_editor):
    """Until now every device had one layout; it becomes the "Front" area of its disks."""
    Disk = apps.get_model("netbox_utilities", "Disk")
    DiskBayLayout = apps.get_model("netbox_utilities", "DiskBayLayout")
    for layout in DiskBayLayout.objects.all():
        Disk.objects.filter(device_id=layout.device_id, bay__isnull=True).update(bay_id=layout.pk)


def name_field():
    return models.CharField(
        default="Front",
        help_text="z. B. Front, Rückseite, BOSS-Karte (M.2) oder PCIe",
        max_length=50,
        verbose_name="Bereich",
    )


def weight_field():
    return models.PositiveSmallIntegerField(
        default=100,
        help_text="Bereiche mit kleinerem Wert werden zuerst angezeigt.",
        verbose_name="Reihenfolge",
    )


def rows_field():
    return models.PositiveSmallIntegerField(
        default=1,
        help_text="Wie viele Reihen der Bereich hat, z. B. 2 für 2 × 12 Einschübe.",
        validators=[
            django.core.validators.MinValueValidator(1),
            django.core.validators.MaxValueValidator(64),
        ],
        verbose_name="Reihen",
    )


def first_slot_field():
    return models.PositiveSmallIntegerField(
        default=0,
        help_text="Nummer des ersten Steckplatzes laut Hersteller (meist 0 oder 1).",
        validators=[django.core.validators.MaxValueValidator(255)],
        verbose_name="Erster Steckplatz",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "__latest__"),
        ("netbox_utilities", "0009_disks"),
    ]

    operations = [
        # Several areas per device and per device type instead of exactly one layout.
        migrations.AlterField(
            model_name="diskbaylayout",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="netbox_utilities_disk_bays",
                to="dcim.device",
                verbose_name="Gerät",
            ),
        ),
        migrations.AlterField(
            model_name="diskbaytemplate",
            name="device_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="netbox_utilities_disk_bay_templates",
                to="dcim.devicetype",
                verbose_name="Gerätetyp",
            ),
        ),
        migrations.AddField(model_name="diskbaylayout", name="name", field=name_field()),
        migrations.AddField(model_name="diskbaylayout", name="weight", field=weight_field()),
        migrations.AddField(model_name="diskbaytemplate", name="name", field=name_field()),
        migrations.AddField(model_name="diskbaytemplate", name="weight", field=weight_field()),
        migrations.AlterField(model_name="diskbaylayout", name="rows", field=rows_field()),
        migrations.AlterField(model_name="diskbaytemplate", name="rows", field=rows_field()),
        migrations.AlterField(model_name="diskbaylayout", name="first_slot", field=first_slot_field()),
        migrations.AlterField(model_name="diskbaytemplate", name="first_slot", field=first_slot_field()),
        migrations.AlterModelOptions(
            name="diskbaylayout",
            options={
                "ordering": ("device", "weight", "name"),
                "verbose_name": "Steckplatz-Bereich",
                "verbose_name_plural": "Steckplatz-Bereiche",
            },
        ),
        migrations.AlterModelOptions(
            name="diskbaytemplate",
            options={
                "ordering": ("device_type", "weight", "name"),
                "verbose_name": "Datenträger-Vorlage",
                "verbose_name_plural": "Datenträger-Vorlagen",
            },
        ),
        migrations.AddConstraint(
            model_name="diskbaylayout",
            constraint=models.UniqueConstraint(
                fields=("device", "name"), name="netbox_utilities_diskbaylayout_unique_name"
            ),
        ),
        migrations.AddConstraint(
            model_name="diskbaytemplate",
            constraint=models.UniqueConstraint(
                fields=("device_type", "name"), name="netbox_utilities_diskbaytemplate_unique_name"
            ),
        ),
        # Disks belong to an area; slot numbers are unique per area.
        migrations.AddField(
            model_name="disk",
            name="bay",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="disks",
                to="netbox_utilities.diskbaylayout",
                verbose_name="Bereich",
            ),
        ),
        migrations.RemoveConstraint(model_name="disk", name="netbox_utilities_disk_unique_occupied_slot"),
        migrations.AddConstraint(
            model_name="disk",
            constraint=models.UniqueConstraint(
                condition=~models.Q(status="replaced"),
                fields=("bay", "slot"),
                name="netbox_utilities_disk_unique_occupied_slot",
                violation_error_message="Dieser Steckplatz ist bereits bestückt.",
            ),
        ),
        migrations.AlterModelOptions(
            name="disk",
            options={
                "ordering": ("device", "bay__weight", "bay__name", "slot", "-install_date", "pk"),
                "verbose_name": "Datenträger",
                "verbose_name_plural": "Datenträger",
            },
        ),
        # Data step last: PostgreSQL refuses ALTER TABLE after row updates with pending FK triggers.
        migrations.RunPython(assign_disks_to_existing_layouts, migrations.RunPython.noop),
    ]
