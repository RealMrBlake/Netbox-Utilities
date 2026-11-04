from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from netbox.models import NetBoxModel
from utilities.choices import ChoiceSet

from . import disks, hardware


class NavigationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="netbox_utilities_navigation",
    )
    menu_order = models.JSONField(default=list, blank=True)
    hidden_menus = models.JSONField(default=list, blank=True)
    sidebar_collapsed = models.BooleanField(default=False)
    sidebar_width = models.PositiveSmallIntegerField(
        default=288,
        validators=[MinValueValidator(216), MaxValueValidator(408)],
    )
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user",)

    def __str__(self):
        return f"Navigation for {self.user}"


class UtilitiesSettings(models.Model):
    singleton_id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=1,
        editable=False,
        validators=[MinValueValidator(1)],
    )
    tenant_filter_enabled = models.BooleanField(default=True)
    tenant_required = models.BooleanField(default=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "NetBox Utilities setting"
        verbose_name_plural = "NetBox Utilities settings"

    def save(self, *args, **kwargs):
        self.singleton_id = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return "NetBox Utilities settings"


class DeviceRackPlacement(models.Model):
    WIDTH_CHOICES = (
        (2, "1/2 Rackbreite"),
        (3, "1/3 Rackbreite"),
        (4, "1/4 Rackbreite"),
    )

    device = models.OneToOneField(
        "dcim.Device",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_rack_placement",
    )
    width = models.PositiveSmallIntegerField(choices=WIDTH_CHOICES)
    horizontal_position = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text="Position von links innerhalb der Rackbreite.",
    )
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=models.Q(width__gte=models.F("horizontal_position")),
                name="netbox_utilities_placement_position_within_width",
            ),
        )
        verbose_name = "Gerätebreite im Rack"
        verbose_name_plural = "Gerätebreiten im Rack"

    def __str__(self):
        return f"{self.device}: 1/{self.width}, Position {self.horizontal_position}"


class SwitchStack(models.Model):
    """A switch that represents a stack; its members are shown one below the other in the port panel."""

    device = models.OneToOneField(
        "dcim.Device",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_switch_stack",
    )
    members = models.ManyToManyField(
        "dcim.Device",
        blank=True,
        related_name="netbox_utilities_stack_memberships",
    )
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Switch-Stack"
        verbose_name_plural = "Switch-Stacks"

    def __str__(self):
        return f"Stack {self.device}"


class CableVLANAssignment(models.Model):
    cable = models.OneToOneField(
        "dcim.Cable",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_vlan_assignment",
    )
    vlans = models.ManyToManyField(
        "ipam.VLAN",
        related_name="netbox_utilities_cable_assignments",
        blank=True,
    )
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "VLAN-Zuordnung einer Kabelverbindung"
        verbose_name_plural = "VLAN-Zuordnungen von Kabelverbindungen"

    def __str__(self):
        return f"VLANs für Kabel {self.cable}"


class WirelessLinkVLANAssignment(models.Model):
    wireless_link = models.OneToOneField(
        "wireless.WirelessLink",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_vlan_assignment",
    )
    vlans = models.ManyToManyField(
        "ipam.VLAN",
        related_name="netbox_utilities_wireless_link_assignments",
        blank=True,
    )
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "VLAN-Zuordnung einer Funkverbindung"
        verbose_name_plural = "VLAN-Zuordnungen von Funkverbindungen"

    def __str__(self):
        return f"VLANs für Funkverbindung {self.wireless_link}"


DEFAULT_BAY_NAME = "Front"
BAY_LAYOUT_FIELDS = ("name", "weight", "slot_count", "rows", "first_slot", "numbering", "form_factor")


class DiskStatusChoices(ChoiceSet):
    key = "Disk.status"

    CHOICES = [
        (disks.STATUS_ACTIVE, "Aktiv", "green"),
        (disks.STATUS_SPARE, "Hot-Spare", "cyan"),
        (disks.STATUS_FAILED, "Defekt", "red"),
        (disks.STATUS_PLANNED, "Geplant", "blue"),
        (disks.STATUS_REPLACED, "Ausgebaut / ersetzt", "gray"),
    ]


class DiskTypeChoices(ChoiceSet):
    CHOICES = [
        ("hdd", "HDD"),
        ("ssd", "SSD"),
        ("nvme", "NVMe-SSD"),
        ("other", "Sonstiges"),
    ]


class DiskInterfaceChoices(ChoiceSet):
    CHOICES = [
        ("sata", "SATA"),
        ("sas", "SAS"),
        ("nvme", "NVMe (PCIe)"),
        ("scsi", "SCSI"),
        ("fc", "Fibre Channel"),
        ("usb", "USB"),
        ("other", "Sonstiges"),
    ]


class DiskFormFactorChoices(ChoiceSet):
    CHOICES = [
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


class SlotNumberingChoices(ChoiceSet):
    CHOICES = [
        (disks.NUMBERING_HORIZONTAL, "Zeilenweise (links → rechts)"),
        (disks.NUMBERING_VERTICAL, "Spaltenweise (oben → unten)"),
    ]


class RAIDLevelChoices(ChoiceSet):
    CHOICES = list(disks.RAID_LEVELS.items())


class DiskBayLayoutBase(NetBoxModel):
    name = models.CharField(
        "Bereich",
        max_length=50,
        default=DEFAULT_BAY_NAME,
        help_text="z. B. Front, Rückseite, BOSS-Karte (M.2) oder PCIe",
    )
    weight = models.PositiveSmallIntegerField(
        "Reihenfolge", default=100, help_text="Bereiche mit kleinerem Wert werden zuerst angezeigt."
    )
    slot_count = models.PositiveSmallIntegerField(
        "Anzahl Steckplätze",
        validators=[MinValueValidator(1), MaxValueValidator(512)],
    )
    rows = models.PositiveSmallIntegerField(
        "Reihen",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(64)],
        help_text="Wie viele Reihen der Bereich hat, z. B. 2 für 2 × 12 Einschübe.",
    )
    first_slot = models.PositiveSmallIntegerField(
        "Erster Steckplatz",
        default=0,
        validators=[MaxValueValidator(255)],
        help_text="Nummer des ersten Steckplatzes laut Hersteller (meist 0 oder 1).",
    )
    numbering = models.CharField(
        "Nummerierung",
        max_length=20,
        choices=SlotNumberingChoices,
        default=disks.NUMBERING_HORIZONTAL,
    )
    form_factor = models.CharField("Bauform", max_length=20, choices=DiskFormFactorChoices, blank=True)

    class Meta:
        abstract = True

    @property
    def last_slot(self):
        return self.first_slot + self.slot_count - 1

    def layout_values(self):
        return {name: getattr(self, name) for name in BAY_LAYOUT_FIELDS}


class DiskBayTemplate(DiskBayLayoutBase):
    """Remembers the slot areas of a device type so new devices skip the wizard."""

    device_type = models.ForeignKey(
        "dcim.DeviceType",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_disk_bay_templates",
        verbose_name="Gerätetyp",
    )

    class Meta:
        ordering = ("device_type", "weight", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("device_type", "name"), name="netbox_utilities_diskbaytemplate_unique_name"
            ),
        )
        verbose_name = "Datenträger-Vorlage"
        verbose_name_plural = "Datenträger-Vorlagen"

    def __str__(self):
        return f"{self.device_type}: {self.name} ({self.slot_count} Steckplätze)"

    def get_absolute_url(self):
        return reverse("plugins:netbox_utilities:diskbaytemplate", args=[self.pk])


class DiskBayLayout(DiskBayLayoutBase):
    """One slot area of a device, e.g. the 16 front bays or a PCIe card with two NVMe SSDs."""

    device = models.ForeignKey(
        "dcim.Device",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_disk_bays",
        verbose_name="Gerät",
    )

    class Meta:
        ordering = ("device", "weight", "name")
        constraints = (
            models.UniqueConstraint(fields=("device", "name"), name="netbox_utilities_diskbaylayout_unique_name"),
        )
        verbose_name = "Steckplatz-Bereich"
        verbose_name_plural = "Steckplatz-Bereiche"

    def __str__(self):
        return f"{self.device}: {self.name}"

    def get_absolute_url(self):
        return reverse("dcim:device_disks", kwargs={"pk": self.device_id})

    def clean(self):
        super().clean()
        if self.pk and self.slot_count:
            outside = list(
                Disk.objects.filter(bay_id=self.pk, status__in=disks.SLOT_OCCUPYING_STATUSES)
                .exclude(slot__range=(self.first_slot, self.last_slot))
                .values_list("slot", flat=True)
            )
            if outside:
                raise ValidationError(
                    "Diese Steckplätze sind noch bestückt und lägen außerhalb des Bereichs: "
                    + ", ".join(str(slot) for slot in sorted(outside))
                )


class RAIDGroup(NetBoxModel):
    device = models.ForeignKey(
        "dcim.Device",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_raid_groups",
        verbose_name="Gerät",
    )
    name = models.CharField("Name", max_length=100)
    level = models.CharField("RAID-Level", max_length=20, choices=RAIDLevelChoices)
    spans = models.PositiveSmallIntegerField(
        "Spans",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(16)],
        help_text="Nur für RAID 50/60: Anzahl der Unter-Arrays.",
    )
    description = models.CharField("Beschreibung", max_length=200, blank=True)

    class Meta:
        ordering = ("device", "name")
        constraints = (
            models.UniqueConstraint(fields=("device", "name"), name="netbox_utilities_raidgroup_unique_name"),
        )
        verbose_name = "RAID-Gruppe"
        verbose_name_plural = "RAID-Gruppen"

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_utilities:raidgroup", args=[self.pk])

    @property
    def members(self):
        return [disk for disk in self.disks.all() if disk.status in (disks.STATUS_ACTIVE, disks.STATUS_FAILED)]

    @property
    def hot_spares(self):
        return [disk for disk in self.disks.all() if disk.status == disks.STATUS_SPARE]

    @property
    def capacity(self):
        """(usable GB, tolerated failures, error) for the current members."""
        return disks.raid_usable_capacity(self.level, [disk.capacity_gb for disk in self.members], self.spans)

    @property
    def usable_capacity_gb(self):
        return self.capacity[0]

    @property
    def usable_capacity_display(self):
        return disks.format_capacity(self.usable_capacity_gb)

    @property
    def is_degraded(self):
        return any(disk.status == disks.STATUS_FAILED for disk in self.members)


class Disk(NetBoxModel):
    device = models.ForeignKey(
        "dcim.Device",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_disks",
        verbose_name="Gerät",
    )
    bay = models.ForeignKey(
        DiskBayLayout,
        on_delete=models.PROTECT,
        related_name="disks",
        blank=True,
        null=True,
        verbose_name="Bereich",
    )
    slot = models.PositiveSmallIntegerField("Steckplatz")
    status = models.CharField("Status", max_length=20, choices=DiskStatusChoices, default=disks.STATUS_ACTIVE)
    disk_type = models.CharField("Typ", max_length=20, choices=DiskTypeChoices, blank=True)
    interface = models.CharField("Schnittstelle", max_length=20, choices=DiskInterfaceChoices, blank=True)
    form_factor = models.CharField("Bauform", max_length=20, choices=DiskFormFactorChoices, blank=True)
    manufacturer = models.CharField("Hersteller", max_length=100, blank=True)
    model = models.CharField("Modell", max_length=100, blank=True)
    capacity_gb = models.PositiveIntegerField("Größe (GB)", blank=True, null=True)
    serial = models.CharField("Seriennummer", max_length=100, blank=True, db_index=True)
    firmware = models.CharField("Firmware", max_length=50, blank=True)
    manufacture_date = models.DateField("Herstellungsdatum", blank=True, null=True)
    install_date = models.DateField("Einbaudatum", blank=True, null=True)
    removal_date = models.DateField("Ausbaudatum", blank=True, null=True)
    warranty_end = models.DateField("Garantie bis", blank=True, null=True)
    raid_group = models.ForeignKey(
        RAIDGroup,
        on_delete=models.SET_NULL,
        related_name="disks",
        blank=True,
        null=True,
        verbose_name="RAID-Gruppe",
    )
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.PROTECT,
        related_name="netbox_utilities_disks",
        blank=True,
        null=True,
        verbose_name="Mandant",
        help_text="Wird automatisch vom Gerät übernommen.",
    )
    description = models.CharField("Beschreibung", max_length=200, blank=True)
    comments = models.TextField("Kommentare", blank=True)

    clone_fields = (
        "device",
        "bay",
        "status",
        "disk_type",
        "interface",
        "form_factor",
        "manufacturer",
        "model",
        "capacity_gb",
        "firmware",
        "manufacture_date",
        "install_date",
        "warranty_end",
        "raid_group",
    )

    class Meta:
        ordering = ("device", "bay__weight", "bay__name", "slot", "-install_date", "pk")
        constraints = (
            models.UniqueConstraint(
                fields=("bay", "slot"),
                condition=~models.Q(status=disks.STATUS_REPLACED),
                name="netbox_utilities_disk_unique_occupied_slot",
                violation_error_message="Dieser Steckplatz ist bereits bestückt.",
            ),
        )
        verbose_name = "Datenträger"
        verbose_name_plural = "Datenträger"

    def __str__(self):
        label = " ".join(part for part in (self.manufacturer, self.model) if part) or "Datenträger"
        return f"{label} ({self.serial})" if self.serial else f"{label} – {self.slot_label}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_utilities:disk", args=[self.pk])

    def get_status_color(self):
        return DiskStatusChoices.colors.get(self.status)

    @property
    def capacity_display(self):
        return disks.format_capacity(self.capacity_gb)

    @property
    def slot_label(self):
        return f"{self.bay.name} {self.slot}" if self.bay_id else f"Slot {self.slot}"

    @property
    def occupies_slot(self):
        return self.status in disks.SLOT_OCCUPYING_STATUSES

    @property
    def warnings(self):
        return disks.disk_warnings(self, **disks.warning_settings())

    def sync_tenant(self):
        # The tenant always follows the device and cannot be chosen per disk.
        if self.device_id:
            self.tenant_id = self.device.tenant_id

    def clean(self):
        self.sync_tenant()
        super().clean()
        errors = {}
        if self.device_id:
            bay = self.bay if self.bay_id else None
            if bay is None and DiskBayLayout.objects.filter(device_id=self.device_id).exists():
                errors["bay"] = "Bitte den Bereich wählen, in dem der Datenträger steckt."
            elif bay is not None and bay.device_id != self.device_id:
                errors["bay"] = "Der Bereich gehört zu einem anderen Gerät."
            elif bay is not None and self.slot is not None and not bay.first_slot <= self.slot <= bay.last_slot:
                errors["slot"] = f"{bay.name} hat nur die Steckplätze {bay.first_slot} bis {bay.last_slot}."
            if self.raid_group_id and self.raid_group.device_id != self.device_id:
                errors["raid_group"] = "Die RAID-Gruppe gehört zu einem anderen Gerät."
        if self.status == disks.STATUS_REPLACED and not self.removal_date:
            self.removal_date = timezone.localdate()
        if self.install_date and self.manufacture_date and self.install_date < self.manufacture_date:
            errors["install_date"] = "Das Einbaudatum liegt vor dem Herstellungsdatum."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.sync_tenant()
        if self.status == disks.STATUS_REPLACED and not self.removal_date:
            self.removal_date = timezone.localdate()
        return super().save(*args, **kwargs)


#
# CPU & RAM
#


class CPUManufacturerChoices(ChoiceSet):
    CHOICES = [
        ("intel", "Intel"),
        ("amd", "AMD"),
        ("other", "Sonstiges"),
    ]


class MemoryTypeChoices(ChoiceSet):
    CHOICES = list(hardware.MEMORY_TYPES.items())


class CPUModel(NetBoxModel):
    """One entry of the CPU catalogue; the built-in entries come from cpu_catalog.py."""

    manufacturer = models.CharField("Hersteller", max_length=20, choices=CPUManufacturerChoices)
    family = models.CharField(
        "Familie", max_length=100, blank=True, help_text="z. B. Xeon Scalable 3. Gen (Ice Lake-SP)"
    )
    name = models.CharField("Modell", max_length=100, help_text="z. B. Xeon Gold 6338 oder EPYC 7543")
    cores = models.PositiveSmallIntegerField("Kerne", validators=[MinValueValidator(1), MaxValueValidator(1024)])
    threads = models.PositiveSmallIntegerField("Threads", validators=[MinValueValidator(1), MaxValueValidator(2048)])
    base_clock_ghz = models.DecimalField("Basistakt (GHz)", max_digits=4, decimal_places=2)
    boost_clock_ghz = models.DecimalField("Turbo (GHz)", max_digits=4, decimal_places=2, blank=True, null=True)
    tdp_watts = models.PositiveSmallIntegerField("TDP (W)", blank=True, null=True)
    socket = models.CharField("Sockel", max_length=30, blank=True)
    launch_year = models.PositiveSmallIntegerField("Erscheinungsjahr", blank=True, null=True)
    max_sockets = models.PositiveSmallIntegerField(
        "Max. Sockel",
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        help_text="Wie viele CPUs dieses Modells ein System höchstens haben kann.",
    )
    builtin = models.BooleanField("Aus dem Katalog", default=False, editable=False)
    customized = models.BooleanField("Angepasst", default=False, editable=False)
    description = models.CharField("Beschreibung", max_length=200, blank=True)

    class Meta:
        ordering = ("manufacturer", "-launch_year", "name")
        constraints = (
            models.UniqueConstraint(fields=("manufacturer", "name"), name="netbox_utilities_cpumodel_unique_name"),
        )
        verbose_name = "CPU-Modell"
        verbose_name_plural = "CPU-Modelle"

    def __str__(self):
        return f"{self.get_manufacturer_display()} {self.name}" if self.manufacturer != "other" else self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_utilities:cpumodel", args=[self.pk])

    @property
    def clock_display(self):
        base = hardware.format_clock(self.base_clock_ghz)
        return f"{base} / {hardware.format_clock(self.boost_clock_ghz)}" if self.boost_clock_ghz else base

    @property
    def summary(self):
        """ "32 Kerne / 64 Threads, 2,0 / 3,2 GHz" for selects and panels."""
        return f"{self.cores} Kerne / {self.threads} Threads, {self.clock_display}"

    def clean(self):
        super().clean()
        if self.cores and self.threads and self.threads < self.cores:
            raise ValidationError({"threads": "Es kann nicht weniger Threads als Kerne geben."})
        if self.base_clock_ghz and self.boost_clock_ghz and self.boost_clock_ghz < self.base_clock_ghz:
            raise ValidationError({"boost_clock_ghz": "Der Turbo-Takt liegt unter dem Basistakt."})


class DeviceHardware(NetBoxModel):
    """CPU and RAM of one device (server or virtualization host)."""

    device = models.OneToOneField(
        "dcim.Device",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_hardware",
        verbose_name="Gerät",
    )
    cpu = models.ForeignKey(
        CPUModel,
        on_delete=models.PROTECT,
        related_name="devices",
        blank=True,
        null=True,
        verbose_name="CPU-Modell",
    )
    cpu_count = models.PositiveSmallIntegerField(
        "Anzahl CPUs",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        help_text="Bestückte Sockel",
    )
    memory_gb = models.PositiveIntegerField("RAM gesamt (GB)", blank=True, null=True)
    memory_type = models.CharField("RAM-Typ", max_length=20, choices=MemoryTypeChoices, blank=True)
    memory_modules = models.PositiveSmallIntegerField(
        "Anzahl Module", blank=True, null=True, validators=[MaxValueValidator(256)]
    )
    memory_module_gb = models.PositiveIntegerField("Modulgröße (GB)", blank=True, null=True)
    memory_speed_mts = models.PositiveIntegerField(
        "Takt (MT/s)", blank=True, null=True, help_text="z. B. 3200 oder 4800"
    )
    description = models.CharField("Beschreibung", max_length=200, blank=True)
    comments = models.TextField("Kommentare", blank=True)

    class Meta:
        ordering = ("device",)
        verbose_name = "CPU & RAM"
        verbose_name_plural = "CPU & RAM"

    def __str__(self):
        return f"{self.device} – CPU & RAM"

    def get_absolute_url(self):
        return reverse("plugins:netbox_utilities:devicehardware", args=[self.pk])

    @property
    def total_cores(self):
        return self.cpu.cores * self.cpu_count if self.cpu_id else None

    @property
    def total_threads(self):
        return self.cpu.threads * self.cpu_count if self.cpu_id else None

    @property
    def cpu_display(self):
        if not self.cpu_id:
            return "—"
        return f"{self.cpu_count} × {self.cpu}" if self.cpu_count > 1 else str(self.cpu)

    @property
    def memory_display(self):
        return hardware.format_memory(self.memory_gb)

    @property
    def memory_detail(self):
        """ "12 × 32 GB DDR4-3200"."""
        parts = []
        if self.memory_modules and self.memory_module_gb:
            parts.append(f"{self.memory_modules} × {self.memory_module_gb} GB")
        kind = self.get_memory_type_display() if self.memory_type else ""
        if kind and self.memory_speed_mts:
            kind = f"{kind}-{self.memory_speed_mts}"
        elif self.memory_speed_mts:
            kind = f"{self.memory_speed_mts} MT/s"
        if kind:
            parts.append(kind)
        return " ".join(parts)

    def clean(self):
        super().clean()
        if not self.memory_gb and self.memory_modules and self.memory_module_gb:
            self.memory_gb = self.memory_modules * self.memory_module_gb
        if self.cpu_id and self.cpu_count and self.cpu_count > self.cpu.max_sockets:
            raise ValidationError({"cpu_count": f"{self.cpu} unterstützt höchstens {self.cpu.max_sockets} Sockel."})
