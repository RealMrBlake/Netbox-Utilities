import django.core.validators
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

STATUS_CHOICES = [
    ("active", "Aktiv"),
    ("spare", "Hot-Spare"),
    ("failed", "Defekt"),
    ("planned", "Geplant"),
    ("replaced", "Ausgebaut / ersetzt"),
]
TYPE_CHOICES = [("hdd", "HDD"), ("ssd", "SSD"), ("nvme", "NVMe-SSD"), ("other", "Sonstiges")]
INTERFACE_CHOICES = [
    ("sata", "SATA"),
    ("sas", "SAS"),
    ("nvme", "NVMe (PCIe)"),
    ("scsi", "SCSI"),
    ("fc", "Fibre Channel"),
    ("usb", "USB"),
    ("other", "Sonstiges"),
]
FORM_FACTOR_CHOICES = [
    ("3.5", '3,5"'),
    ("2.5", '2,5"'),
    ("1.8", '1,8"'),
    ("m2", "M.2"),
    ("u2", "U.2"),
    ("u3", "U.3"),
    ("e1s", "E1.S"),
    ("e3s", "E3.S"),
    ("aic", "PCIe-Karte"),
    ("other", "Sonstiges"),
]
NUMBERING_CHOICES = [
    ("horizontal", "Zeilenweise (links → rechts)"),
    ("vertical", "Spaltenweise (oben → unten)"),
]
RAID_LEVEL_CHOICES = [
    ("raid0", "RAID 0"),
    ("raid1", "RAID 1"),
    ("raid5", "RAID 5"),
    ("raid6", "RAID 6"),
    ("raid10", "RAID 10"),
    ("raid50", "RAID 50"),
    ("raid60", "RAID 60"),
    ("raidz1", "RAID-Z1"),
    ("raidz2", "RAID-Z2"),
    ("raidz3", "RAID-Z3"),
    ("jbod", "JBOD"),
    ("other", "Sonstiges"),
]


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


def layout_fields():
    return [
        (
            "slot_count",
            models.PositiveSmallIntegerField(
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(512),
                ],
                verbose_name="Anzahl Steckplätze",
            ),
        ),
        (
            "rows",
            models.PositiveSmallIntegerField(
                default=1,
                help_text="Wie viele Reihen die Gerätefront hat, z. B. 2 für 2 × 12 Einschübe.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(64),
                ],
                verbose_name="Reihen",
            ),
        ),
        (
            "first_slot",
            models.PositiveSmallIntegerField(
                default=0,
                help_text="Nummer des ersten Steckplatzes laut Hersteller (meist 0 oder 1).",
                validators=[django.core.validators.MaxValueValidator(1)],
                verbose_name="Erster Steckplatz",
            ),
        ),
        (
            "numbering",
            models.CharField(
                choices=NUMBERING_CHOICES, default="horizontal", max_length=20, verbose_name="Nummerierung"
            ),
        ),
        (
            "form_factor",
            models.CharField(blank=True, choices=FORM_FACTOR_CHOICES, max_length=20, verbose_name="Bauform"),
        ),
    ]


def tags_field():
    return ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag"))


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "__latest__"),
        ("extras", "__latest__"),
        ("tenancy", "__latest__"),
        ("netbox_utilities", "0008_connection_vlan_assignments"),
    ]

    operations = [
        migrations.CreateModel(
            name="DiskBayTemplate",
            fields=[
                *netbox_model_fields(),
                *layout_fields(),
                (
                    "device_type",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_disk_bay_template",
                        to="dcim.devicetype",
                        verbose_name="Gerätetyp",
                    ),
                ),
                tags_field(),
            ],
            options={
                "ordering": ("device_type",),
                "verbose_name": "Datenträger-Vorlage",
                "verbose_name_plural": "Datenträger-Vorlagen",
            },
        ),
        migrations.CreateModel(
            name="DiskBayLayout",
            fields=[
                *netbox_model_fields(),
                *layout_fields(),
                (
                    "device",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_disk_bay_layout",
                        to="dcim.device",
                        verbose_name="Gerät",
                    ),
                ),
                tags_field(),
            ],
            options={
                "ordering": ("device",),
                "verbose_name": "Steckplatz-Layout",
                "verbose_name_plural": "Steckplatz-Layouts",
            },
        ),
        migrations.CreateModel(
            name="RAIDGroup",
            fields=[
                *netbox_model_fields(),
                ("name", models.CharField(max_length=100, verbose_name="Name")),
                ("level", models.CharField(choices=RAID_LEVEL_CHOICES, max_length=20, verbose_name="RAID-Level")),
                (
                    "spans",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text="Nur für RAID 50/60: Anzahl der Unter-Arrays.",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(16),
                        ],
                        verbose_name="Spans",
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=200, verbose_name="Beschreibung")),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_raid_groups",
                        to="dcim.device",
                        verbose_name="Gerät",
                    ),
                ),
                tags_field(),
            ],
            options={
                "ordering": ("device", "name"),
                "verbose_name": "RAID-Gruppe",
                "verbose_name_plural": "RAID-Gruppen",
                "constraints": [
                    models.UniqueConstraint(fields=("device", "name"), name="netbox_utilities_raidgroup_unique_name")
                ],
            },
        ),
        migrations.CreateModel(
            name="Disk",
            fields=[
                *netbox_model_fields(),
                ("slot", models.PositiveSmallIntegerField(verbose_name="Steckplatz")),
                (
                    "status",
                    models.CharField(choices=STATUS_CHOICES, default="active", max_length=20, verbose_name="Status"),
                ),
                ("disk_type", models.CharField(blank=True, choices=TYPE_CHOICES, max_length=20, verbose_name="Typ")),
                (
                    "interface",
                    models.CharField(
                        blank=True, choices=INTERFACE_CHOICES, max_length=20, verbose_name="Schnittstelle"
                    ),
                ),
                (
                    "form_factor",
                    models.CharField(blank=True, choices=FORM_FACTOR_CHOICES, max_length=20, verbose_name="Bauform"),
                ),
                ("manufacturer", models.CharField(blank=True, max_length=100, verbose_name="Hersteller")),
                ("model", models.CharField(blank=True, max_length=100, verbose_name="Modell")),
                ("capacity_gb", models.PositiveIntegerField(blank=True, null=True, verbose_name="Größe (GB)")),
                (
                    "serial",
                    models.CharField(blank=True, db_index=True, max_length=100, verbose_name="Seriennummer"),
                ),
                ("firmware", models.CharField(blank=True, max_length=50, verbose_name="Firmware")),
                ("manufacture_date", models.DateField(blank=True, null=True, verbose_name="Herstellungsdatum")),
                ("install_date", models.DateField(blank=True, null=True, verbose_name="Einbaudatum")),
                ("removal_date", models.DateField(blank=True, null=True, verbose_name="Ausbaudatum")),
                ("warranty_end", models.DateField(blank=True, null=True, verbose_name="Garantie bis")),
                ("description", models.CharField(blank=True, max_length=200, verbose_name="Beschreibung")),
                ("comments", models.TextField(blank=True, verbose_name="Kommentare")),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_disks",
                        to="dcim.device",
                        verbose_name="Gerät",
                    ),
                ),
                (
                    "raid_group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disks",
                        to="netbox_utilities.raidgroup",
                        verbose_name="RAID-Gruppe",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        help_text="Wird automatisch vom Gerät übernommen.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="netbox_utilities_disks",
                        to="tenancy.tenant",
                        verbose_name="Mandant",
                    ),
                ),
                tags_field(),
            ],
            options={
                "ordering": ("device", "slot", "-install_date", "pk"),
                "verbose_name": "Datenträger",
                "verbose_name_plural": "Datenträger",
                "constraints": [
                    models.UniqueConstraint(
                        condition=~models.Q(status="replaced"),
                        fields=("device", "slot"),
                        name="netbox_utilities_disk_unique_occupied_slot",
                        violation_error_message="Dieser Steckplatz ist bereits bestückt.",
                    )
                ],
            },
        ),
    ]
