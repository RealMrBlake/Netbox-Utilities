import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_utilities", "0002_utilitiessettings_tenant_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="navigationpreference",
            name="sidebar_collapsed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="navigationpreference",
            name="sidebar_width",
            field=models.PositiveSmallIntegerField(
                default=288,
                validators=[
                    django.core.validators.MinValueValidator(216),
                    django.core.validators.MaxValueValidator(408),
                ],
            ),
        ),
    ]
