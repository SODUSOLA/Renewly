"""report emails: user opt-out and the periodic-email dispatch log

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# func to add the opt-out column and the dispatch table
def upgrade() -> None:
    """Add users.report_emails (everyone starts opted in) and the email_dispatch table."""
    op.add_column("users", sa.Column("report_emails", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_table(
        "email_dispatch",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_email_dispatch_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_dispatch")),
        sa.UniqueConstraint("user_id", "kind", "period", name="uq_email_dispatch_dedup"),
    )
    op.create_index(op.f("ix_email_dispatch_user_id"), "email_dispatch", ["user_id"], unique=False)


# func to undo it
def downgrade() -> None:
    """Drop the dispatch table and the opt-out column."""
    op.drop_index(op.f("ix_email_dispatch_user_id"), table_name="email_dispatch")
    op.drop_table("email_dispatch")
    op.drop_column("users", "report_emails")
