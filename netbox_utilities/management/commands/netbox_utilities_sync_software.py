from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Transfer the software lists of inventory reports (NetBox Windows Agent, NetBox Synchronizer) "
        "in device comments into netbox-slm installations."
    )

    def add_arguments(self, parser):
        parser.add_argument("--device", type=int, action="append", help="Only this device ID (repeatable)")

    def handle(self, *args, **options):
        from dcim.models import Device
        from django.db.models import Q

        from netbox_utilities.software_sync import sync_device_software

        devices = Device.objects.filter(
            Q(comments__icontains="installed software") | Q(comments__icontains="installierte software")
        )
        if options.get("device"):
            devices = devices.filter(pk__in=options["device"])

        total_created = total_removed = synced = 0
        for device in devices.iterator():
            try:
                created, removed = sync_device_software(device)
            except Exception as error:  # noqa: BLE001 - report the device and continue with the next one
                self.stderr.write(f"{device} (#{device.pk}): {error}")
                continue
            synced += 1
            total_created += created
            total_removed += removed
            if created or removed:
                self.stdout.write(f"{device}: +{created} / -{removed}")
        self.stdout.write(
            self.style.SUCCESS(
                f"{synced} Geräte abgeglichen, {total_created} Installationen angelegt, {total_removed} entfernt."
            )
        )
