"""
The planner decides WHICH tools to call and in what order, given a goal.
Deterministic intent classifier, not an LLM.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, Optional

StepKind = Literal["full_calendar", "corpus_search", "filing_prep"]


@dataclass
class PlanStep:
    kind: StepKind
    args: dict = field(default_factory=dict)
    reason: str = ""


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep]
    planner: str


_FILING_WORDS = ("file", "filing", "submit", "prepare aoc", "prepare the", "prepare a")
_LEGAL_QUESTION_WORDS = ("what is", "what does", "why", "when must", "explain", "does")


def build_plan(
    goal: str, obligation_id: Optional[str] = None, subject_id: Optional[str] = None,
) -> Plan:
    g = goal.lower()

    if any(w in g for w in _FILING_WORDS) and obligation_id:
        steps = [
            PlanStep("full_calendar", {}, "get the whole picture, including dependency status, "
                                            "before touching any one filing"),
            PlanStep("filing_prep", {"obligation_id": obligation_id, "subject_id": subject_id},
                      "assemble the draft — requires human approval downstream, "
                      "and refuses outright if blocked or if no director was specified"),
        ]
        return Plan(goal=goal, steps=steps, planner="rule_based")

    if any(w in g for w in _LEGAL_QUESTION_WORDS):
        steps = [PlanStep("corpus_search", {"question": goal}, "answer must be grounded in the corpus")]
        return Plan(goal=goal, steps=steps, planner="rule_based")

    steps = [
        PlanStep("full_calendar", {}, "determine every applicable obligation and its status"),
        PlanStep("corpus_search", {"question": goal}, "attach explanatory citations"),
    ]
    return Plan(goal=goal, steps=steps, planner="rule_based")