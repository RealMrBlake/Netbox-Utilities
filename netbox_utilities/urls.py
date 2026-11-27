from django.apps import apps
from django.urls import include, path
from netbox.plugins import get_plugin_config
from utilities.urls import get_model_urls

from . import devicetype_views, disk_views, hardware_views, switch_port_views, views  # noqa: F401 - hardware_views registers its model views

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
    path(
        "device-types/export-yaml/",
        devicetype_views.DeviceTypeBulkYAMLExportView.as_view(),
        name="devicetype_bulk_yaml",
    ),
    path(
        "device-types/<int:pk>/export.yaml",
        devicetype_views.DeviceTypeYAMLExportView.as_view(),
        name="devicetype_yaml",
    ),
    path("settings/", views.UtilitiesSettingsView.as_view(), name="settings"),
    path("tenant/select/", views.SelectTenantView.as_view(), name="select_tenant"),
    # Datenträger
    path("disks/import-msa/", disk_views.MSADiskImportView.as_view(), name="disk_msa_import"),
    path("disks/by-device/", disk_views.DiskByDeviceView.as_view(), name="disk_by_device"),
    path("disks/", include(get_model_urls("netbox_utilities", "disk", detail=False))),
    path("disks/<int:pk>/", include(get_model_urls("netbox_utilities", "disk"))),
    path("disks/<int:pk>/replace/", disk_views.DiskReplaceView.as_view(), name="disk_replace"),
    path("raid-groups/", include(get_model_urls("netbox_utilities", "raidgroup", detail=False))),
    path("raid-groups/<int:pk>/", include(get_model_urls("netbox_utilities", "raidgroup"))),
    path("disk-templates/", include(get_model_urls("netbox_utilities", "diskbaytemplate", detail=False))),
    path("disk-templates/<int:pk>/", include(get_model_urls("netbox_utilities", "diskbaytemplate"))),
    # CPU & RAM
    path("cpu-models/", include(get_model_urls("netbox_utilities", "cpumodel", detail=False))),
    path("cpu-models/<int:pk>/", include(get_model_urls("netbox_utilities", "cpumodel"))),
    path("hardware/", include(get_model_urls("netbox_utilities", "devicehardware", detail=False))),
    path("hardware/<int:pk>/", include(get_model_urls("netbox_utilities", "devicehardware"))),
    path(
        "devices/<int:pk>/switch-ports.pdf",
        switch_port_views.SwitchPortsPDFView.as_view(),
        name="device_switch_ports_pdf",
    ),
    path("devices/<int:pk>/disks/setup/", disk_views.DeviceDiskSetupView.as_view(), name="device_disk_setup"),
    path("devices/<int:pk>/disks/fill/", disk_views.DeviceDiskBulkFillView.as_view(), name="device_disk_fill"),
    path("devices/<int:pk>/disks/move/", disk_views.DeviceDiskMoveView.as_view(), name="device_disk_move"),
]

if get_plugin_config("netbox_utilities", "software_enabled") and apps.is_installed("netbox_slm"):
    from . import software_views

    urlpatterns.extend(
        [
            path("software/", software_views.SoftwareOverviewView.as_view(), name="software_overview"),
            path(
                "software/<int:pk>/latest/",
                software_views.SoftwareLatestVersionView.as_view(),
                name="software_latest_version",
            ),
        ]
    )
