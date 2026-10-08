"""Request and response shapes for the vehicles endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# func to turn a plate into its stored form: uppercase, no spaces
def normalize_plate(value: str) -> str:
    """Uppercase a plate number and strip all whitespace ('abc 123' -> 'ABC123')."""
    return "".join(value.split()).upper()


# class for the body of POST /vehicles
class VehicleCreate(BaseModel):
    """Body of POST /vehicles."""

    nickname: str = Field(min_length=1, max_length=100)
    plate_number: str = Field(min_length=1, max_length=20)
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    year: int | None = Field(default=None, ge=1900, le=2100)

    # func to normalize the plate before it is validated and stored
    @field_validator("plate_number")
    @classmethod
    def clean_plate(cls, value: str) -> str:
        """Store plates uppercase without spaces so duplicates are detected reliably."""
        plate = normalize_plate(value)
        if not plate:
            raise ValueError("Plate number cannot be blank")
        return plate


# class for the body of PATCH /vehicles/{id}
class VehicleUpdate(BaseModel):
    """Body of PATCH /vehicles/{id}: only the fields sent are changed."""

    nickname: str | None = Field(default=None, min_length=1, max_length=100)
    plate_number: str | None = Field(default=None, min_length=1, max_length=20)
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    year: int | None = Field(default=None, ge=1900, le=2100)

    # func to normalize the plate when one is supplied
    @field_validator("plate_number")
    @classmethod
    def clean_plate(cls, value: str | None) -> str | None:
        """Apply the same plate normalization as on create."""
        if value is None:
            return value
        plate = normalize_plate(value)
        if not plate:
            raise ValueError("Plate number cannot be blank")
        return plate

    # func to block explicit nulls on columns that cannot be empty
    @model_validator(mode="after")
    def required_fields_not_null(self) -> "VehicleUpdate":
        """Reject `{"nickname": null}` / `{"plate_number": null}` (omit the field instead)."""
        for name in ("nickname", "plate_number"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


# class for a vehicle as returned by the API
class VehicleRead(BaseModel):
    """Public view of a vehicle."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nickname: str
    plate_number: str
    make: str | None
    model: str | None
    year: int | None
    created_at: datetime
    updated_at: datetime
