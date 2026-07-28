import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UtilitiesSettings",
            fields=[
                (
                    "singleton_id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                ("tenant_filter_enabled", models.BooleanField(default=True)),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "NetBox Utilities setting",
                "verbose_name_plural": "NetBox Utilities settings",
            },
        ),
        migrations.CreateModel(
            name="NavigationPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("menu_order", models.JSONField(blank=True, default=list)),
                ("hidden_menus", models.JSONField(blank=True, default=list)),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="netbox_utilities_navigation",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("user",)},
        ),
    ]
