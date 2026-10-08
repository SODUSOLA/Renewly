import uuid
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.documents.models import Document


# class: a vehicle owned by a user. Documents (insurance, registration...) can attach to it
class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A vehicle owned by a user. Documents (insurance, registration...) can attach to it.

    A user cannot register the same plate number twice. Deleting a vehicle keeps
    its documents but detaches them (vehicle_id becomes NULL).
    """

    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "plate_number", name="uq_vehicles_user_id_plate_number"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    nickname: Mapped[str] = mapped_column(String(100))
    # Normalize to uppercase without spaces in the service layer.
    plate_number: Mapped[str] = mapped_column(String(20))
    make: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    user: Mapped["User"] = relationship(back_populates="vehicles")
    documents: Mapped[list["Document"]] = relationship(back_populates="vehicle")
