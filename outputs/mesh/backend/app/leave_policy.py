from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LeaveEntitlement, LeaveRequest


def days_in_year(
    start: date, end: date, year: int, counting: str, holidays: list[str] | None = None
) -> int:
    current, end = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
    result = 0
    excluded = set(holidays or [])
    while current <= end:
        result += (
            counting == "calendar" or current.weekday() < 5
        ) and current.isoformat() not in excluded
        current += timedelta(days=1)
    return result


def reserved_days(
    db: Session,
    org: str,
    employee: str,
    year: int,
    counting: str,
    exclude: str | None = None,
    holidays: list[str] | None = None,
) -> int:
    query = select(LeaveRequest).where(
        LeaveRequest.organization_id == org,
        LeaveRequest.employee_id == employee,
        LeaveRequest.status.in_(["pending", "approved"]),
        LeaveRequest.starts_on <= date(year, 12, 31),
        LeaveRequest.ends_on >= date(year, 1, 1),
    )
    if exclude:
        query = query.where(LeaveRequest.id != exclude)
    return sum(
        days_in_year(row.starts_on, row.ends_on, year, counting, holidays)
        for row in db.scalars(query).all()
    )


def require_capacity(
    db: Session, org: str, employee: str, start: date, end: date, exclude: str | None = None
) -> None:
    # Caller holds the employee row lock through transaction completion.
    policies = db.scalars(
        select(LeaveEntitlement).where(
            LeaveEntitlement.organization_id == org,
            LeaveEntitlement.employee_id == employee,
        )
    ).all()
    if not policies:
        return  # Existing unconfigured tenants retain human-reviewed leave workflows.
    by_year = {row.year: row for row in policies}
    for year in range(start.year, end.year + 1):
        policy = by_year.get(year)
        if policy is None:
            raise HTTPException(409, "Leave allowance is not configured for a requested year")
        needed = days_in_year(start, end, year, policy.counting, policy.holidays)
        used = reserved_days(db, org, employee, year, policy.counting, exclude, policy.holidays)
        if used + needed > policy.allowance_days:
            raise HTTPException(409, "Leave allowance is exhausted or reserved by pending requests")
