import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0237_module_remove_local_context_data"),
        ("netbox_utilities", "0011_cpu_ram"),
    ]

    operations = [
        migrations.CreateModel(
            name="SwitchStack",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "device",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_switch_stack",
                        to="dcim.device",
                    ),
                ),
                (
                    "members",
                    models.ManyToManyField(
                        blank=True,
                        related_name="netbox_utilities_stack_memberships",
                        to="dcim.device",
                    ),
                ),
            ],
            options={
                "verbose_name": "Switch-Stack",
                "verbose_name_plural": "Switch-Stacks",
            },
        ),
    ]
