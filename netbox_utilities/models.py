from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class NavigationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="netbox_utilities_navigation",
    )
    menu_order = models.JSONField(default=list, blank=True)
    hidden_menus = models.JSONField(default=list, blank=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user",)

    def __str__(self):
        return f"Navigation for {self.user}"


class UtilitiesSettings(models.Model):
    singleton_id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=1,
        editable=False,
        validators=[MinValueValidator(1)],
    )
    tenant_filter_enabled = models.BooleanField(default=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "NetBox Utilities setting"
        verbose_name_plural = "NetBox Utilities settings"

    def save(self, *args, **kwargs):
        self.singleton_id = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return "NetBox Utilities settings"
