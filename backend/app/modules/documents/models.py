import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.common.enums import DocumentType, enum_values
from app.core.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.reminders.models import ReminderLog
    from app.modules.vehicles.models import Vehicle


DEFAULT_REMINDER_OFFSETS = [90, 30, 14, 7, 1]



# document class
class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A document with an expiry date that the user wants to be reminded about.

    `reminder_offsets` lists how many days before expiry a reminder is sent.
    Status (valid / expiring soon / expired) is derived from `expiry_date`, never
    stored. `deleted_at` implements soft delete; the CHECK constraints keep bad
    data out even if the API layer has a bug.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "expiry_date >= issue_date", name="expiry_after_issue"
        ),
        CheckConstraint(
            "type <> 'custom' OR custom_type_label IS NOT NULL",
            name="custom_label_required",
        ),
        CheckConstraint(
            "0 <= ALL (reminder_offsets)", name="offsets_non_negative"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, native_enum=False, length=30, values_callable=enum_values)
    )
    custom_type_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(150))
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    reminder_offsets: Mapped[list[int]] = mapped_column(
        ARRAY(Integer),
        default=lambda: list(DEFAULT_REMINDER_OFFSETS),
        server_default=text("'{90,30,14,7,1}'::integer[]"),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="documents")
    vehicle: Mapped["Vehicle | None"] = relationship(back_populates="documents")
    renewals: Mapped[list["RenewalHistory"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="RenewalHistory.renewed_on.desc()",
    )
    reminder_logs: Mapped[list["ReminderLog"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    # method that returns whole days from current day until expiry
    def days_until_expiry(self, today: date) -> int:
        """Return whole days from `today` until expiry.

        Negative means already expired. Status is derived, never stored.
        `today` is passed in (in the user's timezone) so this stays testable.
        """
        return (self.expiry_date - today).days


# lass for audit record written each time a document is marked as renewed
class RenewalHistory(UUIDPrimaryKeyMixin, Base):
    """Audit record written each time a document is marked as renewed.

    Captures the old and new expiry dates so the renewal timeline can be shown.
    """

    __tablename__ = "renewal_history"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    previous_expiry: Mapped[date] = mapped_column(Date)
    new_expiry: Mapped[date] = mapped_column(Date)
    renewed_on: Mapped[date] = mapped_column(
        Date, server_default=text("CURRENT_DATE")
    )
    # Currency is assumed NGN in v1. Unused until cost tracking ships in v2.
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="renewals")
