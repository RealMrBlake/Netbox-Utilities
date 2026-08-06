from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_utilities", "0004_patchpanel_port_mappings"),
    ]

    # Kept in the migration graph for installations which already recorded it.
    # Existing devices must not be modified automatically.
    operations = []
