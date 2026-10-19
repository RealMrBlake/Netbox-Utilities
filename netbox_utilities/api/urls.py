from netbox.api.routers import NetBoxRouter

from . import views

app_name = "netbox_utilities-api"

router = NetBoxRouter()
router.register("disks", views.DiskViewSet)
router.register("raid-groups", views.RAIDGroupViewSet)
router.register("disk-bay-layouts", views.DiskBayLayoutViewSet)
router.register("disk-bay-templates", views.DiskBayTemplateViewSet)

urlpatterns = router.urls
