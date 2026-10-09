import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.common.enums import ReminderChannel, ReminderStatus, enum_values
from app.core.base import Base, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from app.modules.documents.models import Document


# class: one row per reminder attempt; the unique key guarantees a reminder is sent once
class ReminderLog(UUIDPrimaryKeyMixin, Base):
    """One row per reminder attempt; the unique key guarantees a reminder is sent once.

    The daily job inserts here before/after sending. A `failed` row can be
    retried later, but a `sent` row never is.
    """

    __tablename__ = "reminder_log"
    __table_args__ = (
        # The dedup key. It includes expiry_date, so after a renewal the same
        # offsets become eligible again with no cleanup needed.
        UniqueConstraint(
            "document_id",
            "offset_days",
            "expiry_date",
            "channel",
            name="uq_reminder_log_dedup",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    offset_days: Mapped[int] = mapped_column(Integer)
    expiry_date: Mapped[date] = mapped_column(Date)
    channel: Mapped[ReminderChannel] = mapped_column(
        Enum(ReminderChannel, native_enum=False, length=20, values_callable=enum_values)
    )
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(ReminderStatus, native_enum=False, length=20, values_callable=enum_values)
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="reminder_logs")
