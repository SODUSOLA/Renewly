"""Response shape for the dashboard endpoint."""
from datetime import date

from pydantic import BaseModel

from app.modules.documents.schemas import DocumentRead


# class for the number of documents in each status group
class DashboardCounts(BaseModel):
    """How many of the user's documents fall in each status group."""

    expired: int
    expiring_soon: int
    valid: int
    total: int


# class for the whole dashboard payload
class DashboardRead(BaseModel):
    """Documents grouped by status, plus counts, for the home screen.

    `today` is the date in the user's timezone that the grouping is based on.
    Every list is ordered by expiry date, soonest first (so the most overdue
    expired documents come first).
    """

    today: date
    counts: DashboardCounts
    expired: list[DocumentRead]
    expiring_soon: list[DocumentRead]
    valid: list[DocumentRead]
