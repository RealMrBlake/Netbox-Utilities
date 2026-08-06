from django.db import migrations


def repair_mappings_and_paths(apps, schema_editor):
    # Runtime models are intentional here: NetBox's CablePath.retrace() is
    # required to refresh the denormalized path data after migration 0005.
    from netbox_utilities.patchpanel import repair_existing_patchpanels

    repair_existing_patchpanels()


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_utilities", "0005_fix_patchpanel_port_number_mappings"),
    ]

    operations = [
        migrations.RunPython(repair_mappings_and_paths, migrations.RunPython.noop),
    ]
