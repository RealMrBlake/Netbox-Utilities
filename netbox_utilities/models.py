from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class NavigationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="netbox_utilities_navigation",
    )
    menu_order = models.JSONField(default=list, blank=True)
    hidden_menus = models.JSONField(default=list, blank=True)
    sidebar_collapsed = models.BooleanField(default=False)
    sidebar_width = models.PositiveSmallIntegerField(
        default=288,
        validators=[MinValueValidator(216), MaxValueValidator(408)],
    )
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
    tenant_required = models.BooleanField(default=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "NetBox Utilities setting"
        verbose_name_plural = "NetBox Utilities settings"

    def save(self, *args, **kwargs):
        self.singleton_id = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return "NetBox Utilities settings"


class DeviceRackPlacement(models.Model):
    WIDTH_CHOICES = (
        (2, "1/2 Rackbreite"),
        (3, "1/3 Rackbreite"),
        (4, "1/4 Rackbreite"),
    )

    device = models.OneToOneField(
        "dcim.Device",
        on_delete=models.CASCADE,
        related_name="netbox_utilities_rack_placement",
    )
    width = models.PositiveSmallIntegerField(choices=WIDTH_CHOICES)
    horizontal_position = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text="Position von links innerhalb der Rackbreite.",
    )
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=models.Q(width__gte=models.F("horizontal_position")),
                name="netbox_utilities_placement_position_within_width",
            ),
        )
        verbose_name = "Gerätebreite im Rack"
        verbose_name_plural = "Gerätebreiten im Rack"

    def __str__(self):
        return f"{self.device}: 1/{self.width}, Position {self.horizontal_position}"
