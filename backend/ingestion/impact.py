"""
When a source changes, which obligations in the register might it affect?
A deliberate heuristic, not an LLM call — only ever produces false
positives (a human dismisses an irrelevant flag), never false negatives
(a real change silently missed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from domain.obligation import Obligation
from .watcher import ChangeEvent

_SECTION_RE = re.compile(r"\b(?:section|sec\.?|s\.)\s*([0-9]+[A-Za-z]?)\b", re.IGNORECASE)
_FORM_CODE_RE = re.compile(r"\b([A-Z]{2,6}-\d{1,2}[A-Z]{0,2})\b")


@dataclass
class ImpactCandidate:
    obligation_id: str
    obligation_title: str
    match_reason: str


def find_affected_obligations(
    event: ChangeEvent,
    obligations: list[Obligation],
) -> list[ImpactCandidate]:
    text = event.diff_preview.lower()
    mentioned_sections = {m.group(1).lower() for m in _SECTION_RE.finditer(text)}
    mentioned_forms = {m.group(1).lower() for m in _FORM_CODE_RE.finditer(event.diff_preview)}

    candidates: list[ImpactCandidate] = []
    for ob in obligations:
        reasons = []
        if ob.act.lower() in text:
            reasons.append(f"Act name '{ob.act}' appears in the change")
        ob_sections = {s.strip().lower() for s in re.split(r"[,/]", ob.section)}
        if mentioned_sections & ob_sections:
            hit = sorted(mentioned_sections & ob_sections)
            reasons.append(f"section {', '.join(hit)} mentioned in the change")
        if ob.authority.split("/")[0].strip().lower() in text:
            reasons.append(f"authority '{ob.authority}' mentioned")
        haystack = (ob.title + " " + " ".join(ob.evidence_kinds)).lower()
        form_hits = {f for f in mentioned_forms if f in haystack}
        if form_hits:
            reasons.append(f"form code {', '.join(sorted(form_hits))} mentioned in the change")

        if reasons:
            candidates.append(ImpactCandidate(
                obligation_id=ob.obligation_id,
                obligation_title=ob.title,
                match_reason="; ".join(reasons),
            ))
    return candidates