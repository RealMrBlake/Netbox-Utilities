from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_utilities", "0005_fix_patchpanel_port_number_mappings"),
    ]

    # Kept in the migration graph for installations which already recorded it.
    # Existing devices and cable paths must not be modified automatically.
    operations = []
