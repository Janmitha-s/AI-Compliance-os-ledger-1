"""
The two models that replace the old "document with an expiry date" idea.

Obligation          = the rule as it exists in law. Nothing to do with any
                      particular company. One row per statutory duty.
ObligationInstance  = that rule as it falls due for ONE company (or one
                      person at that company) in ONE period.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Predicate(BaseModel):
    field: str
    op: Literal["eq", "ne", "in", "not_in", "gte", "lte", "exists", "contains"]
    value: Any = None

    def evaluate(self, profile: dict) -> Optional[bool]:
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


class Anchor(str, Enum):
    AGM_DATE = "AGM_DATE"
    FY_END = "FY_END"
    MONTH_END = "MONTH_END"
    FIXED_DATE = "FIXED_DATE"


class Periodicity(BaseModel):
    type: Literal["ANNUAL", "HALF_YEARLY", "QUARTERLY", "MONTHLY", "TRIENNIAL", "ONE_TIME"]
    anchor: Anchor
    offset_days: int = 0
    fallback_anchor: Optional[Anchor] = None
    fallback_offset_days: Optional[int] = None
    anchor_month: Optional[int] = None
    anchor_day: Optional[int] = None
    note: str = ""


class Obligation(BaseModel):
    obligation_id: str
    version: int = 1
    effective_from: date
    effective_to: Optional[date] = None

    title: str
    authority: str
    act: str
    section: str
    rules: list[str] = Field(default_factory=list)
    source_url: Optional[str] = None

    subject: Literal["ENTITY", "DIRECTOR"] = "ENTITY"
    depends_on: list[str] = Field(default_factory=list)

    applicability: list[Predicate]
    periodicity: Periodicity

    evidence_kinds: list[str] = Field(default_factory=list)
    penalty: str = ""
    severity_base: int = 50

    confidence: Literal["DRAFT", "HUMAN_VERIFIED"] = "DRAFT"
    reviewed_by: Optional[str] = None
    reviewed_on: Optional[date] = None


class InstanceStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    FILED = "FILED"
    VERIFIED = "VERIFIED"
    LATE = "LATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"


class ObligationInstance(BaseModel):
    entity_id: str
    obligation_id: str
    obligation_version: int
    subject_id: str = ""

    period_label: str
    period_start: date
    period_end: date

    due_date: date
    due_date_basis: str

    status: InstanceStatus = InstanceStatus.NOT_STARTED
    filed_on: Optional[date] = None
    evidence_ref: Optional[str] = None
    blocked_reason: Optional[str] = None

    def days_to_due(self, today: date) -> int:
        return (self.due_date - today).days