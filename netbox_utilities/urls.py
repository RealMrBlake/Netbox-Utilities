from django.urls import include, path
from utilities.urls import get_model_urls

from . import disk_views, views

app_name = "netbox_utilities"

urlpatterns = [
    path("images/bulk-upload/", views.BulkImageUploadView.as_view(), name="bulk_image_upload"),
    path("modules/bulk-install/", views.BulkModuleInstallView.as_view(), name="bulk_module_install"),
    path("navigation/", views.NavigationPreferencesView.as_view(), name="navigation_preferences"),
    path("navigation/layout/", views.NavigationLayoutView.as_view(), name="navigation_layout"),
    path(
        "racks/<int:pk>/elevation-svg/",
        views.RackElevationOfflineSVGView.as_view(),
        name="rack_elevation_offline_svg",
    ),
    path("settings/", views.UtilitiesSettingsView.as_view(), name="settings"),
    path("tenant/select/", views.SelectTenantView.as_view(), name="select_tenant"),
    # Datenträger
    path("disks/", include(get_model_urls("netbox_utilities", "disk", detail=False))),
    path("disks/<int:pk>/", include(get_model_urls("netbox_utilities", "disk"))),
    path("disks/<int:pk>/replace/", disk_views.DiskReplaceView.as_view(), name="disk_replace"),
    path("raid-groups/", include(get_model_urls("netbox_utilities", "raidgroup", detail=False))),
    path("raid-groups/<int:pk>/", include(get_model_urls("netbox_utilities", "raidgroup"))),
    path("disk-templates/", include(get_model_urls("netbox_utilities", "diskbaytemplate", detail=False))),
    path("disk-templates/<int:pk>/", include(get_model_urls("netbox_utilities", "diskbaytemplate"))),
    path("devices/<int:pk>/disks/setup/", disk_views.DeviceDiskSetupView.as_view(), name="device_disk_setup"),
    path("devices/<int:pk>/disks/fill/", disk_views.DeviceDiskBulkFillView.as_view(), name="device_disk_fill"),
]
