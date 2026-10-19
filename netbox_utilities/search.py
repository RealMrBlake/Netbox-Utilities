from netbox.search import SearchIndex

from .models import Disk, RAIDGroup


class DiskIndex(SearchIndex):
    model = Disk
    fields = (
        ("serial", 60),
        ("model", 150),
        ("manufacturer", 200),
        ("firmware", 300),
        ("description", 500),
        ("comments", 5000),
    )
    display_attrs = ("device", "slot", "status", "capacity_gb", "tenant")


class RAIDGroupIndex(SearchIndex):
    model = RAIDGroup
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("device", "level")


indexes = [DiskIndex, RAIDGroupIndex]
