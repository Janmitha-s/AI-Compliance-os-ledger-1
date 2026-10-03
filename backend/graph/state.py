"""
The state that flows through every node.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, TypedDict


class ComplianceState(TypedDict, total=False):
    goal: str
    profile: dict
    obligation_id: Optional[str]
    subject_id: Optional[str]
    as_of: date

    plan_steps: list[dict]
    instances: list[dict]
    undetermined: list[dict]
    answer: dict

    filing_draft: Optional[dict]
    filing_refusal_reason: Optional[str]
    approved: bool

    critic_passed: Optional[bool]
    critic_defects: list[str]
    revise_count: int

    final_report: dict