"""HTTP endpoints for managing the current user's vehicles."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.vehicles import service
from app.modules.vehicles.models import Vehicle
from app.modules.vehicles.schemas import VehicleCreate, VehicleRead, VehicleUpdate

# Every route here requires a logged-in user.
router = APIRouter(
    prefix="/vehicles", tags=["vehicles"], dependencies=[Depends(get_current_user)]
)

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Vehicle not found")
_DUPLICATE = HTTPException(
    status.HTTP_409_CONFLICT, "You already have a vehicle with that plate number"
)


# func to list the current user's vehicles
@router.get("", response_model=list[VehicleRead])
def list_vehicles(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Vehicle]:
    """List all vehicles owned by the current user."""
    return service.list_vehicles(db, user)


# func to create a vehicle
@router.post("", response_model=VehicleRead, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    body: VehicleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Vehicle:
    """Create a vehicle. Returns 409 if the user already has that plate."""
    try:
        return service.create_vehicle(db, user, body)
    except service.DuplicatePlate:
        raise _DUPLICATE


# func to fetch one vehicle
@router.get("/{vehicle_id}", response_model=VehicleRead)
def get_vehicle(
    vehicle_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Vehicle:
    """Get one vehicle. Returns 404 if it is missing or belongs to someone else."""
    try:
        return service.get_vehicle(db, user, vehicle_id)
    except service.VehicleNotFound:
        raise _NOT_FOUND


# func to partially update a vehicle
@router.patch("/{vehicle_id}", response_model=VehicleRead)
def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Vehicle:
    """Update the fields sent. Returns 404 if not found, 409 on a duplicate plate."""
    try:
        return service.update_vehicle(db, user, vehicle_id, body)
    except service.VehicleNotFound:
        raise _NOT_FOUND
    except service.DuplicatePlate:
        raise _DUPLICATE


# func to delete a vehicle
@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Delete a vehicle. Its documents are kept and detached."""
    try:
        service.delete_vehicle(db, user, vehicle_id)
    except service.VehicleNotFound:
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)
