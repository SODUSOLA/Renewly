"""HTTP endpoint for onboarding progress."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.onboarding import service
from app.modules.onboarding.schemas import OnboardingProgress

router = APIRouter(prefix="/onboarding", tags=["onboarding"], dependencies=[Depends(get_current_user)])


# func to return what the user has done so far
@router.get("/progress", response_model=OnboardingProgress)
def progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> OnboardingProgress:
    """Counts of documents, vehicles and renewals, for the getting-started checklist."""
    return service.build_progress(db, user)
