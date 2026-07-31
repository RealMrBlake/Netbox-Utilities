from django.urls import path

from . import views

app_name = "netbox_utilities"

urlpatterns = [
    path("modules/bulk-install/", views.BulkModuleInstallView.as_view(), name="bulk_module_install"),
    path("navigation/", views.NavigationPreferencesView.as_view(), name="navigation_preferences"),
    path("navigation/layout/", views.NavigationLayoutView.as_view(), name="navigation_layout"),
    path("settings/", views.UtilitiesSettingsView.as_view(), name="settings"),
    path("tenant/select/", views.SelectTenantView.as_view(), name="select_tenant"),
]
