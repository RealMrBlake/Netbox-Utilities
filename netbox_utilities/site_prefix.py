import re

import django_tables2 as tables
from django import forms
from django.db.models import Q

COLUMN_NAME = "site_prefix"


def first_word(value):
    """Return the first whitespace-delimited word of a value."""
    words = str(value or "").split()
    return words[0] if words else None


def split_prefixes(values):
    """Split filter input such as ["Berlin, DC01", "HH"] into single prefixes."""
    prefixes = []
    for value in values or ():
        for part in re.split(r"[,\s]+", str(value)):
            if part and part not in prefixes:
                prefixes.append(part)
    return prefixes


def site_prefix_query(prefixes, field="site__name"):
    """Match records whose site name starts with one of the prefixes as its first word."""
    query = Q()
    for prefix in prefixes:
        query |= Q(**{f"{field}__iexact": prefix})
        query |= Q(**{f"{field}__iregex": rf"^{re.escape(prefix)}\s"})
    return query


def filter_site_prefix(queryset, name, value):
    prefixes = split_prefixes(value)
    if not prefixes:
        return queryset
    return queryset.filter(site_prefix_query(prefixes))


class SitePrefixColumn(tables.Column):
    """Render the first word of a record's site name."""

    def render(self, value):
        if value is None:
            return None
        return first_word(value.name)


def prepend_to_default_columns(table):
    """Show the prefix column first for users without saved table preferences."""
    defaults = tuple(table.Meta.default_columns)
    table.Meta.default_columns = (
        "pk",
        COLUMN_NAME,
        *(name for name in defaults if name not in {"pk", COLUMN_NAME}),
    )


def insert_into_fieldsets(fieldsets, field_name, after="site_id"):
    """Place the field next to the site filter, or in its own fieldset as a fallback."""
    from utilities.forms.rendering import FieldSet

    result = []
    inserted = False
    for fieldset in fieldsets:
        items = tuple(fieldset.items)
        if not inserted and after in items:
            index = items.index(after) + 1
            fieldset = FieldSet(*items[:index], field_name, *items[index:], name=fieldset.name)
            inserted = True
        result.append(fieldset)
    if not inserted:
        result.append(FieldSet(field_name, name="Prefix"))
    return tuple(result)


def install_site_prefix_filter():
    from dcim.filtersets import DeviceFilterSet, RackFilterSet
    from dcim.forms import DeviceFilterForm, RackFilterForm
    from utilities.filters import MultiValueCharFilter

    for filterset in (DeviceFilterSet, RackFilterSet):
        filterset.base_filters[COLUMN_NAME] = MultiValueCharFilter(
            method=filter_site_prefix,
            label="Site prefix (first word of the site name)",
        )

    for form in (DeviceFilterForm, RackFilterForm):
        form.base_fields[COLUMN_NAME] = forms.CharField(
            required=False,
            label="Prefix",
            help_text="Erstes Wort des Standortnamens, mehrere durch Komma getrennt",
        )
        form.fieldsets = insert_into_fieldsets(form.fieldsets, COLUMN_NAME)


def install_site_prefix_column():
    from dcim.tables import DeviceTable, RackTable
    from utilities.tables import register_table_column

    column = SitePrefixColumn(
        accessor=tables.A("site"),
        verbose_name="Prefix",
        empty_values=(),
        # Der Standortname beginnt mit dem Prefix, sortiert also in derselben Reihenfolge.
        order_by=("site__name",),
    )
    register_table_column(column, COLUMN_NAME, DeviceTable, RackTable)
    prepend_to_default_columns(DeviceTable)
    prepend_to_default_columns(RackTable)
    install_site_prefix_filter()
