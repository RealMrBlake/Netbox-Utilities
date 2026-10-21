from dcim.models import Device, DeviceType
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from netbox.forms import NetBoxModelBulkEditForm, NetBoxModelFilterSetForm, NetBoxModelForm, NetBoxModelImportForm
from tenancy.models import Tenant
from utilities.forms.fields import (
    CommentField,
    CSVChoiceField,
    CSVModelChoiceField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
    TagFilterField,
)
from utilities.forms.rendering import FieldSet
from utilities.forms.widgets import DatePicker

from . import disks, msa_import
from .models import (
    BAY_LAYOUT_FIELDS,
    Disk,
    DiskBayLayout,
    DiskBayTemplate,
    DiskFormFactorChoices,
    DiskInterfaceChoices,
    DiskStatusChoices,
    DiskTypeChoices,
    RAIDGroup,
    RAIDLevelChoices,
)

LAYOUT_FIELDS = BAY_LAYOUT_FIELDS


class CapacityField(forms.CharField):
    """Accepts "4 TB", "960 GB" or "1,92 TB" and returns whole decimal gigabytes."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label", "Größe")
        kwargs.setdefault("required", False)
        kwargs.setdefault("help_text", "z. B. 960 GB, 4 TB oder 1,92 TB – ohne Einheit in GB")
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        if isinstance(value, int):
            return disks.format_capacity(value)
        return value

    def to_python(self, value):
        value = super().to_python(value)
        try:
            return disks.parse_capacity(value)
        except ValueError as error:
            raise ValidationError(str(error)) from None


def _date_field(label, **kwargs):
    return forms.DateField(label=label, required=False, widget=DatePicker(), **kwargs)


class DiskForm(NetBoxModelForm):
    device = DynamicModelChoiceField(label="Gerät", queryset=Device.objects.all(), selector=True)
    bay = DynamicModelChoiceField(
        label="Bereich",
        queryset=DiskBayLayout.objects.all(),
        required=False,
        query_params={"device_id": "$device"},
        help_text="z. B. Front oder PCIe-Karte",
    )
    capacity_gb = CapacityField()
    raid_group = DynamicModelChoiceField(
        label="RAID-Gruppe",
        queryset=RAIDGroup.objects.all(),
        required=False,
        query_params={"device_id": "$device"},
    )
    comments = CommentField()

    fieldsets = (
        FieldSet("device", "bay", "slot", "status", "raid_group", name="Einbauort"),
        FieldSet(
            "disk_type",
            "interface",
            "form_factor",
            "manufacturer",
            "model",
            "capacity_gb",
            "serial",
            "firmware",
            name="Datenträger",
        ),
        FieldSet("manufacture_date", "install_date", "removal_date", "warranty_end", name="Lebenszyklus"),
        FieldSet("description", "tags", name="Sonstiges"),
    )

    class Meta:
        model = Disk
        fields = (
            "device",
            "bay",
            "slot",
            "status",
            "raid_group",
            "disk_type",
            "interface",
            "form_factor",
            "manufacturer",
            "model",
            "capacity_gb",
            "serial",
            "firmware",
            "manufacture_date",
            "install_date",
            "removal_date",
            "warranty_end",
            "description",
            "comments",
            "tags",
        )
        widgets = {
            "manufacture_date": DatePicker(),
            "install_date": DatePicker(),
            "removal_date": DatePicker(),
            "warranty_end": DatePicker(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get("install_date"):
            self.initial["install_date"] = timezone.localdate()


class DiskBayLayoutForm(forms.ModelForm):
    """The wizard for a slot area: asks for the number of slots on the first visit of the tab."""

    save_as_template = forms.BooleanField(
        label="Als Vorlage für den Gerätetyp speichern",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Weitere Geräte dieses Typs übernehmen die Bereiche dann mit einem Klick.",
    )

    class Meta:
        model = DiskBayLayout
        fields = LAYOUT_FIELDS
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "list": "nbu-disk-bay-names"}),
            "weight": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "slot_count": forms.NumberInput(attrs={"class": "form-control", "autofocus": True, "min": 1}),
            "rows": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "first_slot": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "numbering": forms.Select(attrs={"class": "form-select"}),
            "form_factor": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        slot_count, rows = cleaned_data.get("slot_count"), cleaned_data.get("rows")
        if slot_count and rows and rows > slot_count:
            self.add_error("rows", "Es kann nicht mehr Reihen als Steckplätze geben.")
        # "device" is not a form field, so Django skips the unique (device, name) constraint here.
        name = cleaned_data.get("name")
        if name and self.instance.device_id:
            duplicate = DiskBayLayout.objects.filter(device_id=self.instance.device_id, name__iexact=name)
            if duplicate.exclude(pk=self.instance.pk).exists():
                self.add_error("name", f"Das Gerät hat bereits einen Bereich „{name}“.")
        return cleaned_data


class DiskBulkFillForm(forms.Form):
    """Fill several slots with identical disks; only the serial numbers differ."""

    slots = forms.TypedMultipleChoiceField(label="Steckplätze", coerce=int, widget=forms.CheckboxSelectMultiple)
    status = forms.ChoiceField(label="Status", choices=DiskStatusChoices, initial=disks.STATUS_ACTIVE)
    disk_type = forms.ChoiceField(label="Typ", choices=(("", "—"), *DiskTypeChoices), required=False)
    interface = forms.ChoiceField(label="Schnittstelle", choices=(("", "—"), *DiskInterfaceChoices), required=False)
    form_factor = forms.ChoiceField(label="Bauform", choices=(("", "—"), *DiskFormFactorChoices), required=False)
    manufacturer = forms.CharField(label="Hersteller", max_length=100, required=False)
    model = forms.CharField(label="Modell", max_length=100, required=False)
    capacity_gb = CapacityField()
    firmware = forms.CharField(label="Firmware", max_length=50, required=False)
    manufacture_date = _date_field("Herstellungsdatum")
    install_date = _date_field("Einbaudatum", initial=timezone.localdate)
    warranty_end = _date_field("Garantie bis")
    raid_group = forms.ModelChoiceField(label="RAID-Gruppe", queryset=RAIDGroup.objects.none(), required=False)
    serials = forms.CharField(
        label="Seriennummern",
        required=False,
        widget=forms.Textarea(attrs={"rows": 8, "class": "font-monospace", "autocomplete": "off"}),
        help_text=(
            "Eine Seriennummer pro Zeile in Reihenfolge der Steckplätze. Ein Barcode-Scanner kann direkt "
            "hintereinander scannen. Fehlende Seriennummern bleiben leer und können später ergänzt werden."
        ),
    )

    def __init__(self, *args, bay, free_slots, **kwargs):
        super().__init__(*args, **kwargs)
        self.bay = bay
        self.device = device = bay.device
        self.fields["slots"].choices = [(slot, f"Slot {slot}") for slot in free_slots]
        self.fields["raid_group"].queryset = RAIDGroup.objects.filter(device=device)
        for name, field in self.fields.items():
            if name == "slots":
                continue
            widget = field.widget
            css = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs["class"] = f"{css} {widget.attrs.get('class', '')}".strip()

    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        slots = cleaned_data.get("slots") or []
        serials = disks.parse_serials(cleaned_data.get("serials"))
        if len(serials) > len(slots):
            self.add_error(
                "serials",
                f"Es wurden {len(serials)} Seriennummern für {len(slots)} Steckplätze angegeben.",
            )
        if repeated := disks.duplicates(serials):
            self.add_error("serials", "Doppelte Seriennummern: " + ", ".join(repeated))
        existing = (
            list(
                Disk.objects.filter(serial__in=serials, status__in=disks.SLOT_OCCUPYING_STATUSES)
                .select_related("device", "bay")
                .order_by("serial")
            )
            if serials
            else []
        )
        if existing:
            self.add_error(
                "serials",
                "Bereits eingebaut: "
                + ", ".join(f"{disk.serial} ({disk.device}, {disk.slot_label})" for disk in existing),
            )
        cleaned_data["serial_list"] = serials
        return cleaned_data

    def build_disks(self):
        data = self.cleaned_data
        serials = data["serial_list"]
        common = {
            name: data.get(name) or ("" if name not in ("capacity_gb", "raid_group") else None)
            for name in (
                "status",
                "disk_type",
                "interface",
                "form_factor",
                "manufacturer",
                "model",
                "capacity_gb",
                "firmware",
                "raid_group",
            )
        }
        return [
            Disk(
                device=self.device,
                bay=self.bay,
                slot=slot,
                serial=serials[index] if index < len(serials) else "",
                manufacture_date=data.get("manufacture_date"),
                install_date=data.get("install_date"),
                warranty_end=data.get("warranty_end"),
                **common,
            )
            for index, slot in enumerate(sorted(data["slots"]))
        ]


class RAIDGroupForm(NetBoxModelForm):
    device = DynamicModelChoiceField(label="Gerät", queryset=Device.objects.all(), selector=True)
    members = DynamicModelMultipleChoiceField(
        label="Datenträger",
        queryset=Disk.objects.all(),
        required=False,
        query_params={"device_id": "$device", "occupied": "true"},
        help_text="Datenträger im Status Hot-Spare werden als Spare dieser Gruppe geführt.",
    )

    fieldsets = (
        FieldSet("device", "name", "level", "spans", "description", name="RAID-Gruppe"),
        FieldSet("members", name="Mitglieder"),
        FieldSet("tags", name="Tags"),
    )

    class Meta:
        model = RAIDGroup
        fields = ("device", "name", "level", "spans", "description", "tags")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["members"] = list(self.instance.disks.values_list("pk", flat=True))

    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        device = cleaned_data.get("device")
        foreign = [disk for disk in cleaned_data.get("members") or () if device and disk.device_id != device.pk]
        if foreign:
            self.add_error(
                "members", "Diese Datenträger gehören zu einem anderen Gerät: " + ", ".join(map(str, foreign))
            )
        return cleaned_data

    def _save_m2m(self):
        super()._save_m2m()
        members = self.cleaned_data.get("members") or []
        member_ids = [disk.pk for disk in members]
        for disk in Disk.objects.filter(raid_group=self.instance).exclude(pk__in=member_ids):
            disk.snapshot()
            disk.raid_group = None
            disk.save()
        for disk in Disk.objects.filter(pk__in=member_ids).exclude(raid_group=self.instance):
            disk.snapshot()
            disk.raid_group = self.instance
            disk.save()


class DiskBayTemplateForm(NetBoxModelForm):
    device_type = DynamicModelChoiceField(label="Gerätetyp", queryset=DeviceType.objects.all())

    fieldsets = (FieldSet("device_type", *LAYOUT_FIELDS, "tags", name="Vorlage"),)

    class Meta:
        model = DiskBayTemplate
        fields = ("device_type", *LAYOUT_FIELDS, "tags")


class DiskFilterForm(NetBoxModelFilterSetForm):
    model = Disk
    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("device_id", "tenant_id", "raid_group_id", name="Zuordnung"),
        FieldSet("status", "disk_type", "interface", "form_factor", "manufacturer", name="Eigenschaften"),
        FieldSet("warranty", "older_than_years", "has_warnings", name="Lebenszyklus"),
    )
    device_id = DynamicModelMultipleChoiceField(queryset=Device.objects.all(), required=False, label="Gerät")
    tenant_id = DynamicModelMultipleChoiceField(queryset=Tenant.objects.all(), required=False, label="Mandant")
    raid_group_id = DynamicModelMultipleChoiceField(
        queryset=RAIDGroup.objects.all(), required=False, label="RAID-Gruppe"
    )
    status = forms.MultipleChoiceField(choices=DiskStatusChoices, required=False, label="Status")
    disk_type = forms.MultipleChoiceField(choices=DiskTypeChoices, required=False, label="Typ")
    interface = forms.MultipleChoiceField(choices=DiskInterfaceChoices, required=False, label="Schnittstelle")
    form_factor = forms.MultipleChoiceField(choices=DiskFormFactorChoices, required=False, label="Bauform")
    manufacturer = forms.CharField(required=False, label="Hersteller")
    warranty = forms.ChoiceField(
        required=False,
        label="Garantie",
        choices=(("", "—"), ("expired", "Abgelaufen"), ("expiring", "Läuft bald ab"), ("valid", "Gültig")),
    )
    older_than_years = forms.IntegerField(required=False, min_value=1, label="Älter als (Jahre)")
    has_warnings = forms.NullBooleanField(
        required=False,
        label="Mit Warnungen",
        widget=forms.Select(choices=(("", "—"), ("true", "Ja"), ("false", "Nein"))),
    )
    tag = TagFilterField(model)


class RAIDGroupFilterForm(NetBoxModelFilterSetForm):
    model = RAIDGroup
    fieldsets = (FieldSet("q", "filter_id", "tag"), FieldSet("device_id", "level", name="Eigenschaften"))
    device_id = DynamicModelMultipleChoiceField(queryset=Device.objects.all(), required=False, label="Gerät")
    level = forms.MultipleChoiceField(choices=RAIDLevelChoices, required=False, label="RAID-Level")
    tag = TagFilterField(model)


class DiskImportForm(NetBoxModelImportForm):
    device = CSVModelChoiceField(
        label="Gerät", queryset=Device.objects.all(), to_field_name="name", help_text="Name des Geräts"
    )
    status = CSVChoiceField(label="Status", choices=DiskStatusChoices, required=False)
    disk_type = CSVChoiceField(label="Typ", choices=DiskTypeChoices, required=False)
    interface = CSVChoiceField(label="Schnittstelle", choices=DiskInterfaceChoices, required=False)
    form_factor = CSVChoiceField(label="Bauform", choices=DiskFormFactorChoices, required=False)
    capacity = CapacityField(help_text="z. B. 960 GB oder 4 TB")
    bay = forms.CharField(
        label="Bereich",
        required=False,
        help_text="Name des Bereichs, z. B. Front; leer, wenn das Gerät nur einen Bereich hat",
    )
    raid_group = forms.CharField(
        label="RAID-Gruppe",
        required=False,
        help_text="Name einer vorhandenen RAID-Gruppe des Geräts",
    )

    class Meta:
        model = Disk
        fields = (
            "device",
            "bay",
            "slot",
            "status",
            "disk_type",
            "interface",
            "form_factor",
            "manufacturer",
            "model",
            "capacity",
            "serial",
            "firmware",
            "manufacture_date",
            "install_date",
            "removal_date",
            "warranty_end",
            "raid_group",
            "description",
            "comments",
            "tags",
        )

    # bay and raid_group arrive as names. The field cleaners keep the name aside and leave None behind,
    # so the model instance never receives a string, even if clean() stops early on another error.
    def clean_raid_group(self):
        self._raid_group_name = (self.cleaned_data.get("raid_group") or "").strip()

    def clean_bay(self):
        self._bay_name = (self.cleaned_data.get("bay") or "").strip()

    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        if cleaned_data.get("status") in (None, ""):
            cleaned_data["status"] = disks.STATUS_ACTIVE
            self.instance.status = disks.STATUS_ACTIVE
        if (capacity := cleaned_data.get("capacity")) is not None:
            self.instance.capacity_gb = capacity
        device = cleaned_data.get("device")
        bay_name = getattr(self, "_bay_name", "")
        cleaned_data["bay"] = None
        if device:
            bays = list(DiskBayLayout.objects.filter(device=device))
            if bay_name:
                matches = [bay for bay in bays if bay.name.casefold() == bay_name.casefold()]
                if matches:
                    cleaned_data["bay"] = matches[0]
                else:
                    self.add_error("bay", f"Das Gerät {device} hat keinen Bereich „{bay_name}“.")
            elif len(bays) == 1:
                cleaned_data["bay"] = bays[0]
        group_name = getattr(self, "_raid_group_name", "")
        cleaned_data["raid_group"] = None
        if group_name and device:
            group = RAIDGroup.objects.filter(device=device, name=group_name).first()
            if group is None:
                self.add_error("raid_group", f"Das Gerät {device} hat keine RAID-Gruppe „{group_name}“.")
            else:
                cleaned_data["raid_group"] = group
        return cleaned_data


class DiskBulkEditForm(NetBoxModelBulkEditForm):
    model = Disk
    status = forms.ChoiceField(label="Status", choices=(("", "—"), *DiskStatusChoices), required=False)
    disk_type = forms.ChoiceField(label="Typ", choices=(("", "—"), *DiskTypeChoices), required=False)
    interface = forms.ChoiceField(label="Schnittstelle", choices=(("", "—"), *DiskInterfaceChoices), required=False)
    form_factor = forms.ChoiceField(label="Bauform", choices=(("", "—"), *DiskFormFactorChoices), required=False)
    manufacturer = forms.CharField(label="Hersteller", max_length=100, required=False)
    firmware = forms.CharField(label="Firmware", max_length=50, required=False)
    manufacture_date = _date_field("Herstellungsdatum")
    install_date = _date_field("Einbaudatum")
    removal_date = _date_field("Ausbaudatum")
    warranty_end = _date_field("Garantie bis")
    description = forms.CharField(label="Beschreibung", max_length=200, required=False)
    comments = CommentField()

    fieldsets = (
        FieldSet("status", "disk_type", "interface", "form_factor", "manufacturer", "firmware"),
        FieldSet("manufacture_date", "install_date", "removal_date", "warranty_end", name="Lebenszyklus"),
        FieldSet("description", name="Sonstiges"),
    )
    nullable_fields = (
        "disk_type",
        "interface",
        "form_factor",
        "manufacturer",
        "firmware",
        "manufacture_date",
        "install_date",
        "removal_date",
        "warranty_end",
        "description",
        "comments",
    )


class MSAUploadForm(forms.Form):
    """Step 1 of the HPE MSA import: the CSV export from Pools → Disks."""

    export_file = forms.FileField(
        label="CSV-Datei",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv,text/csv"}),
    )
    export_text = forms.CharField(
        label="… oder Inhalt einfügen",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 8}),
    )

    def clean(self):
        cleaned_data = super().clean()
        upload = cleaned_data.get("export_file")
        data = upload.read() if upload else cleaned_data.get("export_text", "")
        if not data or not str(data).strip():
            raise ValidationError("Bitte eine CSV-Datei hochladen oder den Inhalt einfügen.")
        export = msa_import.parse_export(data)
        if not export.disks:
            raise ValidationError(export.errors)
        cleaned_data["export"] = export
        cleaned_data["raw"] = data if isinstance(data, str) else msa_import.decode(data)
        return cleaned_data


class MSAAssignForm(forms.Form):
    """Step 2: which NetBox device is which MSA enclosure (shelf)."""

    create_raid_groups = forms.BooleanField(
        label="RAID-Gruppen aus „Disk Group“ anlegen",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Fehlende Gruppen werden mit RAID-Level „Sonstiges“ angelegt; das Level bitte danach prüfen.",
    )
    replace_existing = forms.BooleanField(
        label="Belegte Steckplätze ersetzen",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Steckt in NetBox ein anderer Datenträger im Steckplatz, wird er als ausgebaut markiert.",
    )
    estimate_install_date = forms.BooleanField(
        label="Einbaudatum aus Betriebsstunden schätzen",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Nur für neue Datenträger; damit greift die Alterswarnung.",
    )

    def __init__(self, *args, enclosures=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.enclosures = list(enclosures)
        for enclosure in self.enclosures:
            self.fields[f"device_{enclosure}"] = DynamicModelChoiceField(
                label=f"Shelf {enclosure}",
                queryset=Device.objects.all(),
                required=False,
                selector=True,
            )

    def device_fields(self):
        return [(enclosure, self[f"device_{enclosure}"]) for enclosure in self.enclosures]

    def option_fields(self):
        return [self[name] for name in ("create_raid_groups", "replace_existing", "estimate_install_date")]

    def clean(self):
        cleaned_data = super().clean()
        assigned = {
            enclosure: cleaned_data.get(f"device_{enclosure}")
            for enclosure in self.enclosures
            if cleaned_data.get(f"device_{enclosure}")
        }
        if not assigned:
            raise ValidationError("Bitte mindestens einem Shelf ein Gerät zuweisen.")
        seen = {}
        for enclosure, device in assigned.items():
            if device.pk in seen:
                self.add_error(f"device_{enclosure}", f"{device} ist bereits Shelf {seen[device.pk]} zugewiesen.")
            seen[device.pk] = enclosure
        cleaned_data["assigned"] = assigned
        return cleaned_data
