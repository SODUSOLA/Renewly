import uuid
from datetime import datetime
from sqlalchemy import DateTime, MetaData, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Predictable constraint names so Alembic migrations are stable and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# class: declarative base for all models; applies the constraint naming convention
class Base(DeclarativeBase):
    """Declarative base for all models; applies the constraint naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# class: adds a UUID primary key, generated in Python and by Postgres as a fallback
class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key, generated in Python and by Postgres as a fallback."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


# class: adds `created_at` and an auto-refreshing `updated_at` (timezone-aware UTC)
class TimestampMixin:
    """Adds `created_at` and an auto-refreshing `updated_at` (timezone-aware UTC)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
