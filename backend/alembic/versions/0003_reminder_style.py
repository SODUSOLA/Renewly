"""reminder style

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# func to add the reminder_style column
def upgrade() -> None:
    """Add users.reminder_style; every existing user keeps today's behaviour ('each')."""
    op.add_column(
        "users",
        sa.Column("reminder_style", sa.String(length=10), server_default="each", nullable=False),
    )


# func to remove the reminder_style column
def downgrade() -> None:
    """Drop users.reminder_style."""
    op.drop_column("users", "reminder_style")
