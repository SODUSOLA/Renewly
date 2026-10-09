"""What a user has done so far, counted from their real data."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.documents.models import Document, RenewalHistory
from app.modules.onboarding.schemas import OnboardingProgress
from app.modules.vehicles.models import Vehicle


# func to count a user's progress
def build_progress(db: Session, user: User) -> OnboardingProgress:
    """Count the user's live documents, vehicles and renewals (and how many renewals have a cost)."""
    documents = db.scalar(
        select(func.count()).select_from(Document).where(Document.user_id == user.id, Document.deleted_at.is_(None))
    )
    vehicles = db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.user_id == user.id))
    renewals, with_cost = db.execute(
        select(func.count(), func.count(RenewalHistory.cost))
        .select_from(RenewalHistory)
        .join(Document, RenewalHistory.document_id == Document.id)
        .where(Document.user_id == user.id, Document.deleted_at.is_(None))
    ).one()
    return OnboardingProgress(documents=documents, vehicles=vehicles, renewals=renewals, renewals_with_cost=with_cost)
