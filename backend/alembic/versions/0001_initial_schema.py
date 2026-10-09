"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() is built into PostgreSQL 13+, so no extension is needed.

    # ---------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="Africa/Lagos", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # ------------------------------------------------------------- vehicles
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("nickname", sa.String(length=100), nullable=False),
        sa.Column("plate_number", sa.String(length=20), nullable=False),
        sa.Column("make", sa.String(length=60), nullable=True),
        sa.Column("model", sa.String(length=60), nullable=True),
        sa.Column("year", sa.SmallInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_vehicles_user_id_users"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicles")),
        sa.UniqueConstraint("user_id", "plate_number", name="uq_vehicles_user_id_plate_number"),
    )
    op.create_index(op.f("ix_vehicles_user_id"), "vehicles", ["user_id"], unique=False)

    # ------------------------------------------------------------ documents
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("custom_type_label", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("document_number", sa.String(length=100), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column(
            "reminder_offsets",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{90,30,14,7,1}'::integer[]"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("expiry_date >= issue_date", name=op.f("ck_documents_expiry_after_issue")),
        sa.CheckConstraint(
            "type <> 'custom' OR custom_type_label IS NOT NULL",
            name=op.f("ck_documents_custom_label_required"),
        ),
        sa.CheckConstraint("0 <= ALL (reminder_offsets)", name=op.f("ck_documents_offsets_non_negative")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_documents_user_id_users"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicles.id"],
            name=op.f("fk_documents_vehicle_id_vehicles"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(op.f("ix_documents_user_id"), "documents", ["user_id"], unique=False)
    op.create_index(op.f("ix_documents_vehicle_id"), "documents", ["vehicle_id"], unique=False)
    op.create_index(op.f("ix_documents_expiry_date"), "documents", ["expiry_date"], unique=False)

    # ------------------------------------------------------ renewal_history
    op.create_table(
        "renewal_history",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("previous_expiry", sa.Date(), nullable=False),
        sa.Column("new_expiry", sa.Date(), nullable=False),
        sa.Column("renewed_on", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name=op.f("fk_renewal_history_document_id_documents"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_renewal_history")),
    )
    op.create_index(
        op.f("ix_renewal_history_document_id"), "renewal_history", ["document_id"], unique=False
    )

    # --------------------------------------------------------- reminder_log
    op.create_table(
        "reminder_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name=op.f("fk_reminder_log_document_id_documents"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminder_log")),
        sa.UniqueConstraint(
            "document_id", "offset_days", "expiry_date", "channel",
            name="uq_reminder_log_dedup",
        ),
    )

    # ------------------------------------------------ password_reset_tokens
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"), "password_reset_tokens", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_password_reset_tokens_token_hash"), "password_reset_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_password_reset_tokens_token_hash"), table_name="password_reset_tokens")
    op.drop_index(op.f("ix_password_reset_tokens_user_id"), table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_table("reminder_log")

    op.drop_index(op.f("ix_renewal_history_document_id"), table_name="renewal_history")
    op.drop_table("renewal_history")

    op.drop_index(op.f("ix_documents_expiry_date"), table_name="documents")
    op.drop_index(op.f("ix_documents_vehicle_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_user_id"), table_name="documents")
    op.drop_table("documents")

    op.drop_index(op.f("ix_vehicles_user_id"), table_name="vehicles")
    op.drop_table("vehicles")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
