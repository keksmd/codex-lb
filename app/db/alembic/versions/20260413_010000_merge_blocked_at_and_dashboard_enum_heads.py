"""merge accounts.blocked_at and dashboard/enum heads

Revision ID: 20260413_010000_merge_blocked_at_and_dashboard_enum_heads
Revises: 20260313_190000_merge_dashboard_and_enum_heads, 20260413_000000_add_accounts_blocked_at
Create Date: 2026-04-13
"""

from __future__ import annotations

revision = "20260413_010000_merge_blocked_at_and_dashboard_enum_heads"
down_revision = (
    "20260313_190000_merge_dashboard_and_enum_heads",
    "20260413_000000_add_accounts_blocked_at",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    return


def downgrade() -> None:
    return
