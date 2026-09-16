"""
materialise() -- turns ONE rule + ONE company into the list of dated things
that company actually owes over the next N months.

This is the function the old codebase was missing. Old flow:

    does the company hold a doc named "AOC-4 Filing Acknowledgement"?
        yes -> compliant, forever

New flow:

    for each financial year in the horizon:
        work out the AGM date (real, or the date it ought to have been)
        due = AGM + 30 days
        is there evidence covering THAT period?
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .obligation import (
    Anchor,
    InstanceStatus,
    Obligation,
    ObligationInstance,
)


def _add_months(d: date, months: int) -> date:
    """Calendar-correct month addition. Clamps to end of month.

    Python's timedelta only knows days, so 'six months after 31 March' has to
    be done by hand. 31 Aug + 6 months must give 28/29 Feb, not crash.
    """
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    # last day of the target month
    if month == 12:
        last = 31
    else:
        last = (date(year, month + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last))


def _financial_years(start: date, horizon_end: date, fy_end_month: int = 3, fy_end_day: int = 31):
    """Yields (label, period_start, period_end) for Indian financial years.

    An Indian FY runs 1 April -> 31 March. We start from the FY that has
    already closed (you cannot file for a year that hasn't ended) and walk
    forward until the horizon.
    """
    # first FY end on or before `start`
    y = start.year
    fy_end = date(y, fy_end_month, fy_end_day)
    if fy_end > start:
        fy_end = date(y - 1, fy_end_month, fy_end_day)

    # go back one extra year so the most recently closed FY is included
    fy_end = date(fy_end.year - 1, fy_end_month, fy_end_day)

    while fy_end <= horizon_end:
        period_start = _add_months(fy_end, -12) + timedelta(days=1)
        label = f"FY{period_start.year}-{str(fy_end.year)[2:]}"
        yield label, period_start, fy_end
        fy_end = date(fy_end.year + 1, fy_end_month, fy_end_day)


def _resolve_due_date(
    obligation: Obligation,
    period_end: date,
    agm_dates: dict[str, date],
    period_label: str,
) -> tuple[date, str]:
    """Returns (due_date, plain-English derivation).

    The derivation string is not decoration. A compliance officer will not
    trust a date they cannot check, so every due date carries its own working.
    """
    p = obligation.periodicity

    if p.anchor == Anchor.AGM_DATE:
        agm = agm_dates.get(period_label)
        if agm is not None:
            due = agm + timedelta(days=p.offset_days)
            return due, (
                f"AGM held {agm:%d %b %Y} + {p.offset_days} days "
                f"({obligation.act} s.{obligation.section})"
            )
        # AGM not recorded -> use the date it ought to have been held
        months = (p.fallback_offset_days or 180) // 30
        deemed = _add_months(period_end, months)
        due = deemed + timedelta(days=p.offset_days)
        return due, (
            f"No AGM date on record. Deemed AGM {deemed:%d %b %Y} "
            f"(FY end {period_end:%d %b %Y} + {months} months) "
            f"+ {p.offset_days} days ({obligation.act} s.{obligation.section})"
        )

    if p.anchor == Anchor.FY_END:
        due = period_end + timedelta(days=p.offset_days)
        return due, f"FY end {period_end:%d %b %Y} + {p.offset_days} days"

    due = period_end + timedelta(days=p.offset_days)
    return due, f"Period end {period_end:%d %b %Y} + {p.offset_days} days"


def is_applicable(obligation: Obligation, profile: dict) -> tuple[Optional[bool], list[str]]:
    """Evaluates every predicate. Returns (verdict, unresolved_fields).

    verdict True  -> applies
            False -> does not apply
            None  -> CANNOT TELL, because the profile is missing something.
                     This bucket must be shown to the user, never swallowed.
    """
    unresolved: list[str] = []
    verdict = True
    for pred in obligation.applicability:
        result = pred.evaluate(profile)
        if result is None:
            unresolved.append(pred.field)
        elif result is False:
            return False, []
    if unresolved:
        return None, unresolved
    return verdict, []


def materialise(
    obligation: Obligation,
    profile: dict,
    today: date,
    horizon_months: int = 18,
    agm_dates: Optional[dict[str, date]] = None,
    evidence_periods: Optional[set[str]] = None,
) -> list[ObligationInstance]:
    """Generate every instance of `obligation` for this company in the horizon.

    evidence_periods = the set of period labels the company has already proved,
    e.g. {"FY2024-25"}. Note this is keyed by PERIOD, which is the whole point:
    proof for FY2024-25 says nothing about FY2025-26.
    """
    agm_dates = agm_dates or {}
    evidence_periods = evidence_periods or set()

    verdict, _ = is_applicable(obligation, profile)
    if verdict is False:
        return []

    horizon_end = _add_months(today, horizon_months)
    instances: list[ObligationInstance] = []

    for label, p_start, p_end in _financial_years(today, horizon_end):
        if obligation.periodicity.type != "ANNUAL":
            continue  # other cadences come later; keep step one small

        due, basis = _resolve_due_date(obligation, p_end, agm_dates, label)
        if due > horizon_end:
            continue

        if label in evidence_periods:
            status = InstanceStatus.FILED
        elif due < today:
            status = InstanceStatus.LATE
        else:
            status = InstanceStatus.NOT_STARTED

        instances.append(
            ObligationInstance(
                entity_id=profile.get("entity_id", profile.get("org_name", "unknown")),
                obligation_id=obligation.obligation_id,
                obligation_version=obligation.version,
                period_label=label,
                period_start=p_start,
                period_end=p_end,
                due_date=due,
                due_date_basis=basis,
                status=status,
            )
        )

    return instances