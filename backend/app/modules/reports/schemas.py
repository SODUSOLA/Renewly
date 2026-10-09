"""Response shapes for the cost reports. All amounts are in naira (the app's v1 currency)."""
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


# class for spending in one calendar month
class MonthCost(BaseModel):
    """Money spent on renewals in one month (1 = January) and how many renewals that was."""

    month: int
    total: Decimal
    renewals: int


# class for spending in one category (a document type)
class CostBucket(BaseModel):
    """Spending grouped by a label such as 'Insurance' or 'Gym membership'."""

    label: str
    total: Decimal
    renewals: int


# class for spending on one vehicle
class VehicleCost(CostBucket):
    """Spending on one vehicle's documents; `vehicle_id` is null for documents with no vehicle."""

    vehicle_id: uuid.UUID | None


# class for a renewal whose cost was never recorded
class MissingCost(BaseModel):
    """A renewal with no cost, so the user can go and fill it in."""

    renewal_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    renewed_on: date


# class for the headline numbers
class CostTotals(BaseModel):
    """Totals for the chosen year, plus the previous year for comparison."""

    total: Decimal
    previous_year_total: Decimal
    renewals: int
    renewals_with_cost: int


# class for the whole report
class CostReport(BaseModel):
    """Everything the reports screen shows for one calendar year.

    Only renewals of documents that still exist are counted. Renewals with no recorded
    cost add nothing to the totals but are counted in `renewals` and listed in `missing_cost`.
    """

    year: int
    currency: str = "NGN"
    available_years: list[int]
    totals: CostTotals
    by_month: list[MonthCost]
    by_type: list[CostBucket]
    by_vehicle: list[VehicleCost]
    missing_cost: list[MissingCost]
    missing_cost_count: int
