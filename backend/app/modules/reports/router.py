"""HTTP endpoints for spending reports."""
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.reports import service
from app.modules.reports.schemas import CostReport

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])

YearParam = Query(default=None, ge=2000, le=2100, description="Calendar year; defaults to this year")


# func to return the cost report
@router.get("/costs", response_model=CostReport)
def cost_report(
    year: int | None = YearParam,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CostReport:
    """What the user spent on renewals in a year: totals, by month, by type and by vehicle."""
    return service.build_cost_report(db, user, year)


# func to download the renewals behind the report
@router.get("/costs.csv")
def cost_report_csv(
    year: int | None = YearParam,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Download the year's renewals (with costs) as a CSV file for spreadsheets or records."""
    used_year, text = service.build_costs_csv(db, user, year)
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="renewly-renewals-{used_year}.csv"'},
    )
