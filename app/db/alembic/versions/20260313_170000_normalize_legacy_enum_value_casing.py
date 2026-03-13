"""normalize legacy uppercase enum-like values to lowercase

Revision ID: 20260313_170000_normalize_legacy_enum_value_casing
Revises: 20260312_120000_add_dashboard_upstream_stream_transport
Create Date: 2026-03-13 17:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "20260313_170000_normalize_legacy_enum_value_casing"
down_revision = "20260312_120000_add_dashboard_upstream_stream_transport"
branch_labels = None
depends_on = None


_ACCOUNT_STATUS_RENAMES: tuple[tuple[str, str], ...] = (
    ("ACTIVE", "active"),
    ("RATE_LIMITED", "rate_limited"),
    ("QUOTA_EXCEEDED", "quota_exceeded"),
    ("PAUSED", "paused"),
    ("DEACTIVATED", "deactivated"),
)

_API_KEY_LIMIT_TYPE_RENAMES: tuple[tuple[str, str], ...] = (
    ("TOTAL_TOKENS", "total_tokens"),
    ("INPUT_TOKENS", "input_tokens"),
    ("OUTPUT_TOKENS", "output_tokens"),
    ("COST_USD", "cost_usd"),
)

_API_KEY_LIMIT_WINDOW_RENAMES: tuple[tuple[str, str], ...] = (
    ("DAILY", "daily"),
    ("WEEKLY", "weekly"),
    ("MONTHLY", "monthly"),
)


def _table_has_column(connection: Connection, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(connection)
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(str(column.get("name")) == column_name for column in columns)


def _normalize_column_values(
    connection: Connection,
    *,
    table_name: str,
    column_name: str,
    renames: tuple[tuple[str, str], ...],
) -> None:
    if not _table_has_column(connection, table_name, column_name):
        return

    for old_value, new_value in renames:
        connection.execute(
            sa.text(
                f"UPDATE {table_name} "
                f"SET {column_name} = :new_value "
                f"WHERE CAST({column_name} AS TEXT) = :old_value"
            ),
            {"old_value": old_value, "new_value": new_value},
        )


def upgrade() -> None:
    bind = op.get_bind()
    _normalize_column_values(
        bind,
        table_name="accounts",
        column_name="status",
        renames=_ACCOUNT_STATUS_RENAMES,
    )
    _normalize_column_values(
        bind,
        table_name="api_key_limits",
        column_name="limit_type",
        renames=_API_KEY_LIMIT_TYPE_RENAMES,
    )
    _normalize_column_values(
        bind,
        table_name="api_key_limits",
        column_name="limit_window",
        renames=_API_KEY_LIMIT_WINDOW_RENAMES,
    )


def downgrade() -> None:
    return
