from django.core.management.base import BaseCommand

from netbox_utilities import cpu_catalog
from netbox_utilities.models import CPUModel


class Command(BaseCommand):
    help = "Load or refresh the built-in Intel/AMD server CPU catalogue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Also reset catalogue entries that were edited in the UI.",
        )

    def handle(self, *args, **options):
        created, updated = cpu_catalog.sync(CPUModel, force=options["force"])
        total = len(list(cpu_catalog.entries()))
        self.stdout.write(
            self.style.SUCCESS(f"CPU-Katalog: {created} neu, {updated} aktualisiert ({total} Modelle im Katalog).")
        )
