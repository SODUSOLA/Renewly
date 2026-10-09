"""Records of periodic emails, so each is sent to each user at most once per period."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import ReminderStatus, enum_values
from app.core.base import Base, UUIDPrimaryKeyMixin


# class for one periodic email to one user for one period
class EmailDispatch(UUIDPrimaryKeyMixin, Base):
    """A "this user, this kind of email, this period" record: the dedup key for periodic emails.

    For the six-monthly report, `kind` is "cost_report" and `period` is like "2026-H1". The unique
    key means only one worker can claim a send; a `failed` row can be retried and a `sent` or
    `skipped` row never is (same idea as reminder_log, which does this for document reminders).
    """

    __tablename__ = "email_dispatch"
    __table_args__ = (UniqueConstraint("user_id", "kind", "period", name="uq_email_dispatch_dedup"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    period: Mapped[str] = mapped_column(String(20))
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(ReminderStatus, native_enum=False, length=20, values_callable=enum_values)
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
