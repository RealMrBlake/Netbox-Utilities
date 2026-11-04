from netbox.api.routers import NetBoxRouter

from . import views

app_name = "netbox_utilities-api"

router = NetBoxRouter()
router.register("disks", views.DiskViewSet)
router.register("raid-groups", views.RAIDGroupViewSet)
router.register("disk-bay-layouts", views.DiskBayLayoutViewSet)
router.register("disk-bay-templates", views.DiskBayTemplateViewSet)
router.register("cpu-models", views.CPUModelViewSet)
router.register("device-hardware", views.DeviceHardwareViewSet)
router.register("switch-stacks", views.SwitchStackViewSet)

urlpatterns = router.urls
