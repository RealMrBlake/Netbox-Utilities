import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def drop_core_rack_position_constraint(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            'ALTER TABLE "dcim_device" DROP CONSTRAINT IF EXISTS "dcim_device_unique_rack_position_face"'
        )


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0237_module_remove_local_context_data"),
        ("netbox_utilities", "0006_retrace_existing_patchpanel_paths"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeviceRackPlacement",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                (
                    "width",
                    models.PositiveSmallIntegerField(
                        choices=[(2, "1/2 Rackbreite"), (3, "1/3 Rackbreite"), (4, "1/4 Rackbreite")]
                    ),
                ),
                (
                    "horizontal_position",
                    models.PositiveSmallIntegerField(
                        help_text="Position von links innerhalb der Rackbreite.",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(4),
                        ],
                    ),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "device",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_rack_placement",
                        to="dcim.device",
                    ),
                ),
            ],
            options={
                "verbose_name": "Gerätebreite im Rack",
                "verbose_name_plural": "Gerätebreiten im Rack",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(width__gte=models.F("horizontal_position")),
                        name="netbox_utilities_placement_position_within_width",
                    )
                ],
            },
        ),
        migrations.RunPython(drop_core_rack_position_constraint, migrations.RunPython.noop),
    ]
