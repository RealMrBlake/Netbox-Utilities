import django.core.validators
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

MANUFACTURER_CHOICES = [("intel", "Intel"), ("amd", "AMD"), ("other", "Sonstiges")]
MEMORY_TYPE_CHOICES = [("ddr3", "DDR3"), ("ddr4", "DDR4"), ("ddr5", "DDR5"), ("other", "Sonstiges")]


def netbox_model_fields():
    return [
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
        ("created", models.DateTimeField(auto_now_add=True, null=True)),
        ("last_updated", models.DateTimeField(auto_now=True, null=True)),
        (
            "custom_field_data",
            models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
        ),
    ]


def tags_field():
    return ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag"))


def load_cpu_catalog(apps, schema_editor):
    from netbox_utilities import cpu_catalog

    cpu_catalog.sync(apps.get_model("netbox_utilities", "CPUModel"))


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "__latest__"),
        ("extras", "__latest__"),
        ("netbox_utilities", "0010_disk_bays"),
    ]

    operations = [
        migrations.CreateModel(
            name="CPUModel",
            fields=[
                *netbox_model_fields(),
                (
                    "manufacturer",
                    models.CharField(choices=MANUFACTURER_CHOICES, max_length=20, verbose_name="Hersteller"),
                ),
                (
                    "family",
                    models.CharField(
                        blank=True,
                        help_text="z. B. Xeon Scalable 3. Gen (Ice Lake-SP)",
                        max_length=100,
                        verbose_name="Familie",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="z. B. Xeon Gold 6338 oder EPYC 7543", max_length=100, verbose_name="Modell"
                    ),
                ),
                (
                    "cores",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(1024),
                        ],
                        verbose_name="Kerne",
                    ),
                ),
                (
                    "threads",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(2048),
                        ],
                        verbose_name="Threads",
                    ),
                ),
                ("base_clock_ghz", models.DecimalField(decimal_places=2, max_digits=4, verbose_name="Basistakt (GHz)")),
                (
                    "boost_clock_ghz",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=4, null=True, verbose_name="Turbo (GHz)"
                    ),
                ),
                ("tdp_watts", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="TDP (W)")),
                ("socket", models.CharField(blank=True, max_length=30, verbose_name="Sockel")),
                (
                    "launch_year",
                    models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Erscheinungsjahr"),
                ),
                (
                    "max_sockets",
                    models.PositiveSmallIntegerField(
                        default=2,
                        help_text="Wie viele CPUs dieses Modells ein System höchstens haben kann.",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(8),
                        ],
                        verbose_name="Max. Sockel",
                    ),
                ),
                ("builtin", models.BooleanField(default=False, editable=False, verbose_name="Aus dem Katalog")),
                ("customized", models.BooleanField(default=False, editable=False, verbose_name="Angepasst")),
                ("description", models.CharField(blank=True, max_length=200, verbose_name="Beschreibung")),
                tags_field(),
            ],
            options={
                "ordering": ("manufacturer", "-launch_year", "name"),
                "verbose_name": "CPU-Modell",
                "verbose_name_plural": "CPU-Modelle",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("manufacturer", "name"), name="netbox_utilities_cpumodel_unique_name"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="DeviceHardware",
            fields=[
                *netbox_model_fields(),
                (
                    "device",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_hardware",
                        to="dcim.device",
                        verbose_name="Gerät",
                    ),
                ),
                (
                    "cpu",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="devices",
                        to="netbox_utilities.cpumodel",
                        verbose_name="CPU-Modell",
                    ),
                ),
                (
                    "cpu_count",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text="Bestückte Sockel",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(8),
                        ],
                        verbose_name="Anzahl CPUs",
                    ),
                ),
                ("memory_gb", models.PositiveIntegerField(blank=True, null=True, verbose_name="RAM gesamt (GB)")),
                (
                    "memory_type",
                    models.CharField(blank=True, choices=MEMORY_TYPE_CHOICES, max_length=20, verbose_name="RAM-Typ"),
                ),
                (
                    "memory_modules",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MaxValueValidator(256)],
                        verbose_name="Anzahl Module",
                    ),
                ),
                (
                    "memory_module_gb",
                    models.PositiveIntegerField(blank=True, null=True, verbose_name="Modulgröße (GB)"),
                ),
                (
                    "memory_speed_mts",
                    models.PositiveIntegerField(
                        blank=True, help_text="z. B. 3200 oder 4800", null=True, verbose_name="Takt (MT/s)"
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=200, verbose_name="Beschreibung")),
                ("comments", models.TextField(blank=True, verbose_name="Kommentare")),
                tags_field(),
            ],
            options={
                "ordering": ("device",),
                "verbose_name": "CPU & RAM",
                "verbose_name_plural": "CPU & RAM",
            },
        ),
        migrations.RunPython(load_cpu_catalog, migrations.RunPython.noop),
    ]
