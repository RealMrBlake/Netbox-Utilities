from django.core.management.base import BaseCommand

from netbox_utilities.patchpanel import repair_existing_patchpanels


class Command(BaseCommand):
    help = "Repair front/rear mappings and cable paths for all devices with the Patchpanel role"

    def handle(self, *args, **options):
        device_count, mapping_count = repair_existing_patchpanels()
        self.stdout.write(
            self.style.SUCCESS(
                f"Repaired {mapping_count} front/rear mappings on {device_count} Patchpanel devices."
            )
        )
