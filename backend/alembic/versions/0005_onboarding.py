"""onboarding state

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# func to add the onboarding column
def upgrade() -> None:
    """Add users.onboarding (a small JSON object of yes/no flags; everyone starts with none)."""
    op.add_column(
        "users",
        sa.Column("onboarding", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )


# func to remove it
def downgrade() -> None:
    """Drop users.onboarding."""
    op.drop_column("users", "onboarding")
