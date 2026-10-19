from typing import TYPE_CHECKING, Annotated

import strawberry
import strawberry_django
from netbox.graphql.types import NetBoxObjectType

from .models import Disk, DiskBayLayout, DiskBayTemplate, RAIDGroup

if TYPE_CHECKING:
    from dcim.graphql.types import DeviceType, DeviceTypeType
    from tenancy.graphql.types import TenantType

LAYOUT_FIELDS = ["id", "slot_count", "rows", "first_slot", "numbering", "form_factor"]


@strawberry_django.type(RAIDGroup, fields=["id", "name", "level", "spans", "description"])
class NetBoxUtilitiesRAIDGroupType(NetBoxObjectType):
    device: Annotated["DeviceType", strawberry.lazy("dcim.graphql.types")]
    disks: list[Annotated["NetBoxUtilitiesDiskType", strawberry.lazy("netbox_utilities.graphql")]]

    @strawberry_django.field
    def usable_capacity_gb(self) -> int | None:
        return self.usable_capacity_gb

    @strawberry_django.field
    def is_degraded(self) -> bool:
        return self.is_degraded


@strawberry_django.type(
    Disk,
    fields=[
        "id",
        "slot",
        "status",
        "disk_type",
        "interface",
        "form_factor",
        "manufacturer",
        "model",
        "capacity_gb",
        "serial",
        "firmware",
        "manufacture_date",
        "install_date",
        "removal_date",
        "warranty_end",
        "description",
        "comments",
    ],
)
class NetBoxUtilitiesDiskType(NetBoxObjectType):
    device: Annotated["DeviceType", strawberry.lazy("dcim.graphql.types")]
    tenant: Annotated["TenantType", strawberry.lazy("tenancy.graphql.types")] | None
    raid_group: Annotated["NetBoxUtilitiesRAIDGroupType", strawberry.lazy("netbox_utilities.graphql")] | None

    @strawberry_django.field
    def warnings(self) -> list[str]:
        return [text for _, text in self.warnings]


@strawberry_django.type(DiskBayLayout, fields=LAYOUT_FIELDS)
class NetBoxUtilitiesDiskBayLayoutType(NetBoxObjectType):
    device: Annotated["DeviceType", strawberry.lazy("dcim.graphql.types")]


@strawberry_django.type(DiskBayTemplate, fields=LAYOUT_FIELDS)
class NetBoxUtilitiesDiskBayTemplateType(NetBoxObjectType):
    device_type: Annotated["DeviceTypeType", strawberry.lazy("dcim.graphql.types")]


@strawberry.type(name="Query")
class NetBoxUtilitiesDiskQuery:
    netbox_utilities_disk: NetBoxUtilitiesDiskType = strawberry_django.field()
    netbox_utilities_disk_list: list[NetBoxUtilitiesDiskType] = strawberry_django.field()
    netbox_utilities_raid_group: NetBoxUtilitiesRAIDGroupType = strawberry_django.field()
    netbox_utilities_raid_group_list: list[NetBoxUtilitiesRAIDGroupType] = strawberry_django.field()
    netbox_utilities_disk_bay_layout: NetBoxUtilitiesDiskBayLayoutType = strawberry_django.field()
    netbox_utilities_disk_bay_layout_list: list[NetBoxUtilitiesDiskBayLayoutType] = strawberry_django.field()
    netbox_utilities_disk_bay_template: NetBoxUtilitiesDiskBayTemplateType = strawberry_django.field()
    netbox_utilities_disk_bay_template_list: list[NetBoxUtilitiesDiskBayTemplateType] = strawberry_django.field()


schema = [NetBoxUtilitiesDiskQuery]
