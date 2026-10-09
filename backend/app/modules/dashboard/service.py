"""Business logic for the dashboard: group a user's documents by status."""
from sqlalchemy.orm import Session

from app.common.dates import today_for
from app.common.enums import DocumentStatus
from app.modules.auth.models import User
from app.modules.dashboard.schemas import DashboardCounts, DashboardRead
from app.modules.documents.schemas import DocumentRead
from app.modules.documents.service import list_documents


# func to split documents into the three status groups
def group_by_status(documents: list[DocumentRead]) -> dict[DocumentStatus, list[DocumentRead]]:
    """Return the documents bucketed by their derived status, order preserved."""
    groups: dict[DocumentStatus, list[DocumentRead]] = {s: [] for s in DocumentStatus}
    for document in documents:
        groups[document.status].append(document)
    return groups


# func to build the dashboard for a user
def build_dashboard(db: Session, user: User) -> DashboardRead:
    """Load the user's live documents and return them grouped with counts.

    Reuses the documents service so the status shown here always matches the
    status shown everywhere else.
    """
    documents = list_documents(db, user)
    groups = group_by_status(documents)
    return DashboardRead(
        today=today_for(user),
        counts=DashboardCounts(
            expired=len(groups[DocumentStatus.EXPIRED]),
            expiring_soon=len(groups[DocumentStatus.EXPIRING_SOON]),
            valid=len(groups[DocumentStatus.VALID]),
            total=len(documents),
        ),
        expired=groups[DocumentStatus.EXPIRED],
        expiring_soon=groups[DocumentStatus.EXPIRING_SOON],
        valid=groups[DocumentStatus.VALID],
    )
