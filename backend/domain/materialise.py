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
    y = start.year
    fy_end = date(y, fy_end_month, fy_end_day)
    if fy_end > start:
        fy_end = date(y - 1, fy_end_month, fy_end_day)

    fy_end = date(fy_end.year - 1, fy_end_month, fy_end_day)

    while fy_end <= horizon_end:
        period_start = _add_months(fy_end, -12) + timedelta(days=1)
        label = f"FY{period_start.year}-{str(fy_end.year)[2:]}"
        yield label, period_start, fy_end
        fy_end = date(fy_end.year + 1, fy_end_month, fy_end_day)


def _half_years(start: date, horizon_end: date, fy_end_month: int = 3, fy_end_day: int = 31):
    """Yields (label, period_start, period_end) for each HALF of each
    financial year: H1 = Apr-Sep, H2 = Oct-Mar. Used by MSME-1, which is
    filed twice a year, not once.
    """
    for fy_label, fy_start, fy_end in _financial_years(start, horizon_end, fy_end_month, fy_end_day):
        h1_end = _add_months(fy_start, 6) - timedelta(days=1)      # 30 Sep
        h1_label = f"{fy_label}-H1"
        yield h1_label, fy_start, h1_end

        h2_start = h1_end + timedelta(days=1)                      # 1 Oct
        h2_label = f"{fy_label}-H2"
        yield h2_label, h2_start, fy_end


def _quarters(start: date, horizon_end: date, fy_end_month: int = 3, fy_end_day: int = 31):
    """Yields (label, period_start, period_end) for each quarter of each FY."""
    for fy_label, fy_start, fy_end in _financial_years(start, horizon_end, fy_end_month, fy_end_day):
        q_start = fy_start
        for q_num in range(1, 5):
            q_end = _add_months(q_start, 3) - timedelta(days=1)
            yield f"{fy_label}-Q{q_num}", q_start, min(q_end, fy_end)
            q_start = q_end + timedelta(days=1)


def _periods_for(
    period_type: str, start: date, horizon_end: date,
    fy_end_month: int = 3, fy_end_day: int = 31,
):
    """Single dispatcher for every cadence a `Periodicity.type` can be.
    Adding a new cadence later means adding one branch here, not touching
    `materialise()` at all — that's the point of factoring it out.
    """
    if period_type in ("ANNUAL", "TRIENNIAL"):
        yield from _financial_years(start, horizon_end, fy_end_month, fy_end_day)
    elif period_type == "HALF_YEARLY":
        yield from _half_years(start, horizon_end, fy_end_month, fy_end_day)
    elif period_type == "QUARTERLY":
        yield from _quarters(start, horizon_end, fy_end_month, fy_end_day)
    elif period_type == "MONTHLY":
        y, m = start.year, start.month
        cursor = date(y, m, 1)
        while cursor <= horizon_end:
            month_end = _add_months(cursor, 1) - timedelta(days=1)
            yield f"{cursor:%Y-%m}", cursor, month_end
            cursor = month_end + timedelta(days=1)
    else:
        raise ValueError(f"no period generator for periodicity type {period_type!r}")


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
        months = (p.fallback_offset_days or 180) // 30
        deemed = _add_months(period_end, months)
        due = deemed + timedelta(days=p.offset_days)
        return due, (
            f"No AGM date on record. Deemed AGM {deemed:%d %b %Y} "
            f"(FY end {period_end:%d %b %Y} + {months} months) "
            f"+ {p.offset_days} days ({obligation.act} s.{obligation.section})"
        )

    if p.anchor == Anchor.FIXED_DATE:
        if p.anchor_month is None or p.anchor_day is None:
            raise ValueError(f"{obligation.obligation_id}: FIXED_DATE anchor needs anchor_month/anchor_day")
        candidate = date(period_end.year, p.anchor_month, p.anchor_day)
        if candidate < period_end:
            candidate = date(period_end.year + 1, p.anchor_month, p.anchor_day)
        return candidate, (
            f"Fixed date {p.anchor_month:02d}-{p.anchor_day:02d} following "
            f"period end {period_end:%d %b %Y} ({obligation.act} s.{obligation.section})"
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
    """Generate every instance of `obligation` for this company (or, for a
    DIRECTOR-subject obligation, for each of its directors) in the horizon.

    evidence_periods = the set of period labels the company has already proved,
    e.g. {"FY2024-25"}. Note this is keyed by PERIOD, which is the whole point:
    proof for FY2024-25 says nothing about FY2025-26.

    For a DIRECTOR-subject obligation, evidence_periods is instead expected
    to be keyed "{DIN}:{period_label}" so one director's filed KYC doesn't
    silently mark another director's as done too.
    """
    agm_dates = agm_dates or {}
    evidence_periods = evidence_periods or set()
    horizon_end = _add_months(today, horizon_months)

    def build_for(subject_profile: dict, entity_id: str, subject_id: str) -> list[ObligationInstance]:
        verdict, _ = is_applicable(obligation, subject_profile)
        if verdict is False:
            return []

        out: list[ObligationInstance] = []
        for label, p_start, p_end in _periods_for(
            obligation.periodicity.type, today, horizon_end,
        ):
            due, basis = _resolve_due_date(obligation, p_end, agm_dates, label)
            if due > horizon_end:
                continue

            evidence_key = f"{subject_id}:{label}" if obligation.subject == "DIRECTOR" else label
            if evidence_key in evidence_periods or label in evidence_periods:
                status = InstanceStatus.FILED
            elif due < today:
                status = InstanceStatus.LATE
            else:
                status = InstanceStatus.NOT_STARTED

            out.append(
                ObligationInstance(
                    entity_id=entity_id,
                    obligation_id=obligation.obligation_id,
                    obligation_version=obligation.version,
                    subject_id=subject_id,
                    period_label=label,
                    period_start=p_start,
                    period_end=p_end,
                    due_date=due,
                    due_date_basis=basis,
                    status=status,
                )
            )
        return out

    entity_id = profile.get("entity_id", profile.get("org_name", "unknown"))

    if obligation.subject == "ENTITY":
        return build_for(profile, entity_id, entity_id)

    instances: list[ObligationInstance] = []
    for director in profile.get("directors", []):
        merged = {**profile, **director}
        din = director.get("din", "UNKNOWN_DIN")
        instances.extend(build_for(merged, entity_id, din))
    return instances


def apply_dependencies(
    instances_by_obligation: dict[str, list[ObligationInstance]],
    obligations_by_id: dict[str, Obligation],
) -> None:
    """Second pass, run AFTER every obligation has been materialised
    independently. Marks a NOT_STARTED instance BLOCKED when an obligation
    it depends_on has not been FILED/VERIFIED for the same period.

    This does not touch due_date — the statute doesn't move AOC-4's deadline
    just because ADT-1 is late — it only changes what a human is told to do
    next: "prepare this" vs. "this is blocked on ADT-1 first".
    """
    for obligation_id, instances in instances_by_obligation.items():
        ob = obligations_by_id.get(obligation_id)
        if not ob or not ob.depends_on:
            continue
        for inst in instances:
            if inst.status not in (InstanceStatus.NOT_STARTED, InstanceStatus.LATE):
                continue
            for dep_id in ob.depends_on:
                dep_instances = instances_by_obligation.get(dep_id, [])
                same_period = [d for d in dep_instances if d.period_label == inst.period_label]
                dep_done = any(d.status in (InstanceStatus.FILED, InstanceStatus.VERIFIED) for d in same_period)
                if not dep_done:
                    inst.status = InstanceStatus.BLOCKED
                    inst.blocked_reason = (
                        f"{dep_id} not yet filed for {inst.period_label}"
                        if same_period else
                        f"{dep_id} has no instance for {inst.period_label} at all"
                    )
                    break