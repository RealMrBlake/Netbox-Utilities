from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_utilities", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="utilitiessettings",
            name="tenant_required",
            field=models.BooleanField(default=True),
        ),
    ]
