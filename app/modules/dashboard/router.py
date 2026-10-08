"""HTTP endpoint for the dashboard."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# func to return the current user's dashboard
@router.get("", response_model=DashboardRead)
def read_dashboard(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DashboardRead:
    """Return the user's documents grouped as expired, expiring soon and valid."""
    return service.build_dashboard(db, user)
