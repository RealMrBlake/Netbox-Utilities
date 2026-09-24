import django_tables2 as tables

COLUMN_NAME = "site_prefix"


def first_word(value):
    """Return the first whitespace-delimited word of a value."""
    words = str(value or "").split()
    return words[0] if words else None


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


def install_site_prefix_column():
    from dcim.tables import DeviceTable, RackTable
    from utilities.tables import register_table_column

    column = SitePrefixColumn(
        accessor=tables.A("site"),
        verbose_name="Prefix",
        empty_values=(),
        orderable=False,
    )
    register_table_column(column, COLUMN_NAME, DeviceTable, RackTable)
    prepend_to_default_columns(DeviceTable)
    prepend_to_default_columns(RackTable)
