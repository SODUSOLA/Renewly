"""Request and response shapes for the documents endpoints."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import DocumentStatus, DocumentType

MAX_OFFSET_DAYS = 365
MAX_OFFSETS = 10


# func to validate and tidy a list of reminder offsets
def clean_offsets(value: list[int]) -> list[int]:
    """Validate reminder offsets and return them de-duplicated, largest first.

    Each offset is "days before expiry" (0 = on the day itself, up to a year).
    """
    if len(value) > MAX_OFFSETS:
        raise ValueError(f"At most {MAX_OFFSETS} reminder offsets are allowed")
    if any(not 0 <= day <= MAX_OFFSET_DAYS for day in value):
        raise ValueError(f"Offsets must be between 0 and {MAX_OFFSET_DAYS} days")
    return sorted(set(value), reverse=True)


# class for the body of POST /documents
class DocumentCreate(BaseModel):
    """Body of POST /documents."""

    vehicle_id: uuid.UUID | None = None
    type: DocumentType
    custom_type_label: str | None = Field(default=None, min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=150)
    document_number: str | None = Field(default=None, max_length=100)
    issue_date: date | None = None
    expiry_date: date
    # Omit to use the default schedule (90, 30, 14, 7 and 1 days before).
    reminder_offsets: list[int] | None = None
    notes: str | None = None

    # func to tidy the offsets when supplied
    @field_validator("reminder_offsets")
    @classmethod
    def tidy_offsets(cls, value: list[int] | None) -> list[int] | None:
        """Validate and sort the offsets (None means "use the default")."""
        return None if value is None else clean_offsets(value)


# class for the body of PATCH /documents/{id}
class DocumentUpdate(BaseModel):
    """Body of PATCH /documents/{id}: only the fields sent are changed.

    Rules that depend on the stored values (custom label, issue/expiry order)
    are checked in the service after merging.
    """

    vehicle_id: uuid.UUID | None = None
    type: DocumentType | None = None
    custom_type_label: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=150)
    document_number: str | None = Field(default=None, max_length=100)
    issue_date: date | None = None
    expiry_date: date | None = None
    reminder_offsets: list[int] | None = None
    notes: str | None = None

    # func to tidy the offsets when supplied
    @field_validator("reminder_offsets")
    @classmethod
    def tidy_offsets(cls, value: list[int] | None) -> list[int] | None:
        """Validate and sort the offsets when they are part of the update."""
        return None if value is None else clean_offsets(value)

    # func to block explicit nulls on columns that cannot be empty
    @model_validator(mode="after")
    def required_fields_not_null(self) -> "DocumentUpdate":
        """Reject explicit nulls for fields that must always have a value."""
        for name in ("type", "title", "expiry_date", "reminder_offsets"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


# class for the body of POST /documents/{id}/renew
class RenewRequest(BaseModel):
    """Body of POST /documents/{id}/renew."""

    new_expiry: date
    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    notes: str | None = None


# class for a document as returned by the API
class DocumentRead(BaseModel):
    """Public view of a document, including its derived status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vehicle_id: uuid.UUID | None
    type: DocumentType
    custom_type_label: str | None
    title: str
    document_number: str | None
    issue_date: date | None
    expiry_date: date
    reminder_offsets: list[int]
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # Derived from expiry_date and the user's "today"; filled in by the service.
    status: DocumentStatus | None = None
    days_left: int | None = None


# class for the body of PATCH /documents/{id}/renewals/{renewal_id}
class RenewalUpdate(BaseModel):
    """Fix or add the cost and notes of a past renewal.

    Unlike most PATCH bodies an explicit `null` is meaningful here: it clears the value.
    Fields that are not sent stay as they are.
    """

    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    notes: str | None = None


# class for one renewal record as returned by the API
class RenewalRead(BaseModel):
    """One entry in a document's renewal history."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    previous_expiry: date
    new_expiry: date
    renewed_on: date
    cost: Decimal | None
    notes: str | None
