"""
The two models that replace the old "document with an expiry date" idea.

Obligation          = the rule as it exists in law. Nothing to do with any
                      particular company. One row per statutory duty.
ObligationInstance  = that rule as it falls due for ONE company in ONE period.
                      "AOC-4 for FY2025-26, due 30 Oct 2026, not yet filed."

The old model could not express the second thing at all, which is why a
company that filed AOC-4 once showed as compliant forever.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- predicates

class Predicate(BaseModel):
    """One machine-evaluable condition on a company profile.

    Example: {"field": "entity_type", "op": "in", "value": ["PRIVATE_LIMITED"]}

    This replaces the hard-coded `if "industry_contains" in rule` checks in the
    old compliance_agent.py. Applicability becomes DATA, not control flow, so a
    new regulation is a new JSON file rather than a new branch in Python.
    """
    field: str
    op: Literal["eq", "ne", "in", "not_in", "gte", "lte", "exists", "contains"]
    value: Any = None

    def evaluate(self, profile: dict) -> Optional[bool]:
        """Returns True / False, or None meaning 'cannot determine'.

        None is the important one. If the company profile is missing the field
        this predicate needs, we must NOT silently treat the obligation as
        not-applicable. Under-reporting an obligation is how clients get fined.
        """
        if self.field not in profile or profile[self.field] is None:
            return None if self.op != "exists" else False

        actual = profile[self.field]
        match self.op:
            case "eq":       return actual == self.value
            case "ne":       return actual != self.value
            case "in":       return actual in self.value
            case "not_in":   return actual not in self.value
            case "gte":      return actual >= self.value
            case "lte":      return actual <= self.value
            case "exists":   return True
            case "contains": return str(self.value).lower() in str(actual).lower()
        return None


# --------------------------------------------------------------- periodicity

class Anchor(str, Enum):
    """The date a due date is counted FROM.

    This is the field the old schema was missing entirely. A licence expires on
    a fixed date; a statutory filing is due N days after an event. Those are
    different shapes and the old code only had the first one.
    """
    AGM_DATE = "AGM_DATE"      # AOC-4, MGT-7, ADT-1
    FY_END = "FY_END"          # DPT-3 style
    MONTH_END = "MONTH_END"    # TDS, PF, ESI
    FIXED_DATE = "FIXED_DATE"  # a hard calendar date each year


class Periodicity(BaseModel):
    type: Literal["ANNUAL", "HALF_YEARLY", "QUARTERLY", "MONTHLY", "TRIENNIAL", "ONE_TIME"]
    anchor: Anchor
    offset_days: int = 0
    # Used when the anchor event did not happen. The Companies Act says an AGM
    # must be held within 6 months of FY end; if it wasn't, the clock still runs
    # from the date it OUGHT to have been held. That is this fallback.
    fallback_anchor: Optional[Anchor] = None
    fallback_offset_days: Optional[int] = None
    note: str = ""


# ------------------------------------------------------------- the obligation

class Obligation(BaseModel):
    obligation_id: str                 # "MCA.AOC4.ANNUAL"
    version: int = 1                   # never edit in place; append a version
    effective_from: date
    effective_to: Optional[date] = None

    title: str
    authority: str
    act: str
    section: str                       # the actual citation, e.g. "137(1)"
    rules: list[str] = Field(default_factory=list)
    source_url: Optional[str] = None

    applicability: list[Predicate]     # ALL must be true
    periodicity: Periodicity

    evidence_kinds: list[str] = Field(default_factory=list)
    penalty: str = ""
    severity_base: int = 50            # 0-100

    confidence: Literal["DRAFT", "HUMAN_VERIFIED"] = "DRAFT"
    reviewed_by: Optional[str] = None
    reviewed_on: Optional[date] = None


# ------------------------------------------------------------- the instance

class InstanceStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    FILED = "FILED"
    VERIFIED = "VERIFIED"
    LATE = "LATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ObligationInstance(BaseModel):
    """One concrete thing that is due, for one company, for one period."""
    entity_id: str
    obligation_id: str
    obligation_version: int

    period_label: str                  # "FY2025-26"
    period_start: date
    period_end: date

    due_date: date
    due_date_basis: str                # human-readable derivation, always shown

    status: InstanceStatus = InstanceStatus.NOT_STARTED
    filed_on: Optional[date] = None
    evidence_ref: Optional[str] = None

    def days_to_due(self, today: date) -> int:
        return (self.due_date - today).days