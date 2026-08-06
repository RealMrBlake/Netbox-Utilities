from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0237_module_remove_local_context_data"),
        ("netbox_utilities", "0003_navigationpreference_sidebar_layout"),
    ]

    # Kept in the migration graph for installations which already recorded it.
    # Existing devices must not be modified automatically.
    operations = []
