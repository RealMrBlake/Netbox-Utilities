import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ipam", "0001_squashed"),
        ("netbox_utilities", "0007_devicerackplacement"),
        ("wireless", "0001_squashed_0008"),
    ]

    operations = [
        migrations.CreateModel(
            name="CableVLANAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "cable",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_vlan_assignment",
                        to="dcim.cable",
                    ),
                ),
                (
                    "vlans",
                    models.ManyToManyField(
                        blank=True,
                        related_name="netbox_utilities_cable_assignments",
                        to="ipam.vlan",
                    ),
                ),
            ],
            options={
                "verbose_name": "VLAN-Zuordnung einer Kabelverbindung",
                "verbose_name_plural": "VLAN-Zuordnungen von Kabelverbindungen",
            },
        ),
        migrations.CreateModel(
            name="WirelessLinkVLANAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "vlans",
                    models.ManyToManyField(
                        blank=True,
                        related_name="netbox_utilities_wireless_link_assignments",
                        to="ipam.vlan",
                    ),
                ),
                (
                    "wireless_link",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_vlan_assignment",
                        to="wireless.wirelesslink",
                    ),
                ),
            ],
            options={
                "verbose_name": "VLAN-Zuordnung einer Funkverbindung",
                "verbose_name_plural": "VLAN-Zuordnungen von Funkverbindungen",
            },
        ),
    ]
