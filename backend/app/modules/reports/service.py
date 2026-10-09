"""Spending reports built from the renewal history.

A renewal is attributed to the calendar year (and month) of its `renewed_on` date, which is
the user's own local date at the time they marked it renewed. Renewals of soft-deleted
documents are left out, consistent with deleted documents disappearing everywhere else.
"""
import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.dates import today_for
from app.common.enums import DocumentType, document_type_label
from app.modules.auth.models import User
from app.modules.documents.models import Document, RenewalHistory
from app.modules.reports.schemas import (
    CostBucket,
    CostReport,
    CostTotals,
    MissingCost,
    MonthCost,
    VehicleCost,
)
from app.modules.vehicles.models import Vehicle

MISSING_COST_LIMIT = 20
ZERO = Decimal("0.00")


# func to restrict a query to the user's live documents' renewals in a date range
def _in_range(query: Select, user: User, start: date, end: date) -> Select:
    """Add the filters shared by every report query: owner, not deleted, `start <= renewed_on < end`."""
    return query.where(
        Document.user_id == user.id,
        Document.deleted_at.is_(None),
        RenewalHistory.renewed_on >= start,
        RenewalHistory.renewed_on < end,
    )


# func to restrict a query to one calendar year
def _in_year(query: Select, user: User, year: int) -> Select:
    """The same filters, for the whole of `year`."""
    return _in_range(query, user, date(year, 1, 1), date(year + 1, 1, 1))


# func to add the join every report query needs
def _from_renewals(*columns) -> Select:
    """SELECT the given columns from renewals joined to their documents."""
    return select(*columns).select_from(RenewalHistory).join(
        Document, RenewalHistory.document_id == Document.id
    )


_COST = func.coalesce(func.sum(RenewalHistory.cost), 0)


# func to sum spending for one year
def _year_total(db: Session, user: User, year: int) -> Decimal:
    """Total recorded cost of the user's renewals in `year`."""
    total = db.scalar(_in_year(_from_renewals(_COST), user, year))
    return Decimal(total).quantize(ZERO)


# func to list the years that have renewals
def available_years(db: Session, user: User, current_year: int) -> list[int]:
    """Years with at least one renewal, newest first, always including the current year."""
    rows = db.scalars(
        _from_renewals(func.extract("year", RenewalHistory.renewed_on))
        .where(Document.user_id == user.id, Document.deleted_at.is_(None))
        .distinct()
    )
    return sorted({int(y) for y in rows} | {current_year}, reverse=True)


# func to build the cost report for a year
def build_cost_report(db: Session, user: User, year: int | None) -> CostReport:
    """Totals, monthly/type/vehicle breakdowns and the renewals missing a cost.

    `year` defaults to the current year in the user's timezone.
    """
    current_year = today_for(user).year
    year = year or current_year

    count, with_cost = db.execute(
        _in_year(_from_renewals(func.count(), func.count(RenewalHistory.cost)), user, year)
    ).one()
    totals = CostTotals(
        total=_year_total(db, user, year),
        previous_year_total=_year_total(db, user, year - 1),
        renewals=count,
        renewals_with_cost=with_cost,
    )

    month_rows = db.execute(
        _in_year(
            _from_renewals(func.extract("month", RenewalHistory.renewed_on), _COST, func.count()),
            user,
            year,
        ).group_by(func.extract("month", RenewalHistory.renewed_on))
    )
    by_month_map = {int(m): (Decimal(t).quantize(ZERO), n) for m, t, n in month_rows}
    by_month = [
        MonthCost(month=m, total=by_month_map.get(m, (ZERO, 0))[0], renewals=by_month_map.get(m, (ZERO, 0))[1])
        for m in range(1, 13)
    ]

    type_rows = db.execute(
        _in_year(_from_renewals(Document.type, Document.custom_type_label, _COST, func.count()), user, year)
        .group_by(Document.type, Document.custom_type_label)
    )
    by_type = sorted(
        (
            CostBucket(label=document_type_label(t, label), total=Decimal(total).quantize(ZERO), renewals=n)
            for t, label, total, n in type_rows
        ),
        key=lambda b: (-b.total, b.label),
    )

    vehicle_rows = db.execute(
        _in_year(
            _from_renewals(Document.vehicle_id, Vehicle.nickname, Vehicle.plate_number, _COST, func.count())
            .outerjoin(Vehicle, Document.vehicle_id == Vehicle.id),
            user,
            year,
        ).group_by(Document.vehicle_id, Vehicle.nickname, Vehicle.plate_number)
    )
    by_vehicle = sorted(
        (
            VehicleCost(
                vehicle_id=vid,
                label=f"{nickname} ({plate})" if vid else "No vehicle",
                total=Decimal(total).quantize(ZERO),
                renewals=n,
            )
            for vid, nickname, plate, total, n in vehicle_rows
        ),
        key=lambda b: (-b.total, b.label),
    )

    missing = db.execute(
        _in_year(
            _from_renewals(RenewalHistory.id, Document.id, Document.title, RenewalHistory.renewed_on)
            .where(RenewalHistory.cost.is_(None)),
            user,
            year,
        )
        .order_by(RenewalHistory.renewed_on.desc(), RenewalHistory.id)
        .limit(MISSING_COST_LIMIT)
    )
    return CostReport(
        year=year,
        available_years=available_years(db, user, current_year),
        totals=totals,
        by_month=by_month,
        by_type=by_type,
        by_vehicle=by_vehicle,
        missing_cost=[
            MissingCost(renewal_id=rid, document_id=did, title=title, renewed_on=on)
            for rid, did, title, on in missing
        ],
        missing_cost_count=count - with_cost,
    )


# func to neutralise spreadsheet formulas in a text cell
def _safe_cell(value: str) -> str:
    """Prefix text that a spreadsheet would run as a formula (CSV injection) with a quote.

    A document titled `=HYPERLINK(...)` must show as text, never execute when the file is opened.
    """
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


# func to export a year's renewals as CSV
def build_costs_csv(db: Session, user: User, year: int | None) -> tuple[int, str]:
    """Return `(year, csv_text)` listing every renewal in the year, oldest first.

    The text starts with a byte-order mark so Excel reads accented or non-English titles correctly.
    """
    year = year or today_for(user).year
    rows = db.execute(
        _in_year(
            _from_renewals(
                RenewalHistory.renewed_on,
                Document.title,
                Document.type,
                Document.custom_type_label,
                Vehicle.nickname,
                Vehicle.plate_number,
                RenewalHistory.previous_expiry,
                RenewalHistory.new_expiry,
                RenewalHistory.cost,
                RenewalHistory.notes,
            ).outerjoin(Vehicle, Document.vehicle_id == Vehicle.id),
            user,
            year,
        ).order_by(RenewalHistory.renewed_on, Document.title, RenewalHistory.id)
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Renewed on", "Document", "Type", "Vehicle", "Previous expiry", "New expiry", "Cost (NGN)", "Notes"])
    for renewed_on, title, doc_type, label, nickname, plate, previous, new, cost, notes in rows:
        writer.writerow(
            [
                renewed_on.isoformat(),
                _safe_cell(title),
                _safe_cell(document_type_label(doc_type, label)),
                _safe_cell(f"{nickname} ({plate})") if nickname else "",
                previous.isoformat(),
                new.isoformat(),
                f"{cost:.2f}" if cost is not None else "",
                _safe_cell(notes or ""),
            ]
        )
    return year, "﻿" + out.getvalue()


# class for a summary of spending over a date range
@dataclass(frozen=True)
class PeriodSummary:
    """Spending between two dates (both inclusive), for periodic emails."""

    start: date
    end: date
    total: Decimal
    previous_total: Decimal
    renewals: int
    renewals_with_cost: int
    by_type: list[CostBucket]
    by_vehicle: list[VehicleCost]

    @property
    def missing_cost_count(self) -> int:
        """Renewals in the period with no recorded cost."""
        return self.renewals - self.renewals_with_cost


# func to total the recorded cost between two dates
def _range_total(db: Session, user: User, start: date, end: date) -> Decimal:
    """Sum of recorded costs for renewals with `start <= renewed_on < end`."""
    return Decimal(db.scalar(_in_range(_from_renewals(_COST), user, start, end))).quantize(ZERO)


# func to summarise spending over a range, with the range just before it for comparison
def build_period_summary(db: Session, user: User, start: date, end: date, *, top: int = 5) -> PeriodSummary:
    """Totals and the biggest types/vehicles for `start..end` (inclusive).

    The comparison figure is the period of equal length immediately before it, so
    "July to December" is compared with the six months before July.
    """
    end_exclusive = end + timedelta(days=1)
    length = end_exclusive - start
    count, with_cost = db.execute(
        _in_range(_from_renewals(func.count(), func.count(RenewalHistory.cost)), user, start, end_exclusive)
    ).one()
    type_rows = db.execute(
        _in_range(_from_renewals(Document.type, Document.custom_type_label, _COST, func.count()), user, start, end_exclusive)
        .group_by(Document.type, Document.custom_type_label)
    )
    by_type = sorted(
        (CostBucket(label=document_type_label(t, lbl), total=Decimal(tot).quantize(ZERO), renewals=n) for t, lbl, tot, n in type_rows),
        key=lambda b: (-b.total, b.label),
    )[:top]
    vehicle_rows = db.execute(
        _in_range(
            _from_renewals(Document.vehicle_id, Vehicle.nickname, Vehicle.plate_number, _COST, func.count())
            .outerjoin(Vehicle, Document.vehicle_id == Vehicle.id),
            user, start, end_exclusive,
        ).group_by(Document.vehicle_id, Vehicle.nickname, Vehicle.plate_number)
    )
    by_vehicle = sorted(
        (
            VehicleCost(vehicle_id=vid, label=f"{nick} ({plate})" if vid else "No vehicle", total=Decimal(tot).quantize(ZERO), renewals=n)
            for vid, nick, plate, tot, n in vehicle_rows
        ),
        key=lambda b: (-b.total, b.label),
    )[:top]
    return PeriodSummary(
        start=start,
        end=end,
        total=_range_total(db, user, start, end_exclusive),
        previous_total=_range_total(db, user, start - length, start),
        renewals=count,
        renewals_with_cost=with_cost,
        by_type=by_type,
        by_vehicle=by_vehicle,
    )


# class for a document that expires soon, with a rough price tag
@dataclass(frozen=True)
class UpcomingExpiry:
    """A live document expiring within the look-ahead window."""

    title: str
    doc_type: DocumentType
    custom_type_label: str | None
    vehicle_label: str | None
    expiry_date: date
    days_left: int
    # What it cost last time it was renewed (None if never renewed or no cost was recorded).
    estimated_cost: Decimal | None


# func to list documents expiring soon with an estimate of what each will cost
def upcoming_expiries(db: Session, user: User, today: date, *, days: int = 183, limit: int = 25) -> list[UpcomingExpiry]:
    """Live documents expiring from today to `today + days`, soonest first (at most `limit`).

    The estimate is the cost of the document's most recent renewal that has one, which is
    usually a good guide to the next bill. It is an estimate, and the emails say so.
    """
    rows = db.execute(
        select(Document, Vehicle)
        .outerjoin(Vehicle, Document.vehicle_id == Vehicle.id)
        .where(
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
            Document.expiry_date >= today,
            Document.expiry_date <= today + timedelta(days=days),
        )
        .order_by(Document.expiry_date, Document.title)
        .limit(limit)
    )
    items = []
    for document, vehicle in rows:
        last_cost = db.scalar(
            select(RenewalHistory.cost)
            .where(RenewalHistory.document_id == document.id, RenewalHistory.cost.is_not(None))
            .order_by(RenewalHistory.renewed_on.desc(), RenewalHistory.id)
            .limit(1)
        )
        items.append(
            UpcomingExpiry(
                title=document.title,
                doc_type=document.type,
                custom_type_label=document.custom_type_label,
                vehicle_label=f"{vehicle.nickname} ({vehicle.plate_number})" if vehicle else None,
                expiry_date=document.expiry_date,
                days_left=(document.expiry_date - today).days,
                estimated_cost=last_cost,
            )
        )
    return items
