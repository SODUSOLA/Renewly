"""Business logic for vehicles. Every query is scoped to the owning user.

A vehicle belonging to someone else is reported as "not found", never "forbidden",
so its existence is not revealed.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.vehicles.schemas import VehicleCreate, VehicleUpdate


# class for "no such vehicle for this user"
class VehicleNotFound(Exception):
    """Raised when the vehicle does not exist or belongs to another user."""


# class for "this user already has that plate"
class DuplicatePlate(Exception):
    """Raised when the user already has a vehicle with the same plate number."""


# func to list the current user's vehicles
def list_vehicles(db: Session, user: User) -> list[Vehicle]:
    """Return all of the user's vehicles, oldest first."""
    return list(
        db.scalars(
            select(Vehicle)
            .where(Vehicle.user_id == user.id)
            .order_by(Vehicle.created_at, Vehicle.id)
        )
    )


# func to fetch one vehicle owned by the current user
def get_vehicle(db: Session, user: User, vehicle_id: uuid.UUID) -> Vehicle:
    """Return the vehicle, or raise VehicleNotFound if it is missing or not theirs."""
    vehicle = db.scalar(
        select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.user_id == user.id)
    )
    if vehicle is None:
        raise VehicleNotFound
    return vehicle


# func to create a vehicle for the current user
def create_vehicle(db: Session, user: User, data: VehicleCreate) -> Vehicle:
    """Create and return a vehicle. Raises DuplicatePlate if the plate is already used."""
    vehicle = Vehicle(user_id=user.id, **data.model_dump())
    db.add(vehicle)
    _commit_or_duplicate(db)
    return vehicle


# func to apply a partial update to a vehicle
def update_vehicle(
    db: Session, user: User, vehicle_id: uuid.UUID, data: VehicleUpdate
) -> Vehicle:
    """Change only the fields the client sent.

    Raises VehicleNotFound or DuplicatePlate.
    """
    vehicle = get_vehicle(db, user, vehicle_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(vehicle, field, value)
    _commit_or_duplicate(db)
    return vehicle


# func to delete a vehicle (its documents are kept, just detached)
def delete_vehicle(db: Session, user: User, vehicle_id: uuid.UUID) -> None:
    """Delete the vehicle. Its documents stay; their vehicle_id becomes NULL."""
    vehicle = get_vehicle(db, user, vehicle_id)
    db.delete(vehicle)
    db.commit()


# func to commit and turn a unique-plate violation into DuplicatePlate
def _commit_or_duplicate(db: Session) -> None:
    """Commit; on a (user, plate) unique violation roll back and raise DuplicatePlate."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicatePlate
