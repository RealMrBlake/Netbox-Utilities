from django.urls import path

from . import views

app_name = "netbox_utilities"

urlpatterns = [
    path("navigation/", views.NavigationPreferencesView.as_view(), name="navigation_preferences"),
    path("settings/", views.UtilitiesSettingsView.as_view(), name="settings"),
    path("tenant/select/", views.SelectTenantView.as_view(), name="select_tenant"),
]
