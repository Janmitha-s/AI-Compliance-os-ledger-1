"""
The Critic. Checks an Answer's INTERNAL CONSISTENCY against evidence
already independently available — does not re-derive the answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from registry.store import RegisterStore
from corpus.index import CorpusIndex

from .retrieval_agent import Answer

_SECTION_IN_CITATION = re.compile(r"s\.([0-9]+[A-Za-z]?(?:\(\d+\))?)")


@dataclass
class Verdict:
    passed: bool
    defects: list[str] = field(default_factory=list)


def review(answer: Answer, register: RegisterStore, corpus: CorpusIndex) -> Verdict:
    defects: list[str] = []

    if not answer.grounded:
        return Verdict(passed=True)

    if not answer.claims:
        return Verdict(passed=False, defects=["grounded=True but there are no claims to support it"])

    known_sections = {
        c.section.lower() for c in corpus.chunks
    } | {
        s.strip().lower()
        for ob in register.all_latest()
        for s in ob.section.split(",")
    }

    for i, claim in enumerate(answer.claims):
        if not claim.citation.strip():
            defects.append(f"claim {i} ('{claim.text[:60]}...') has no citation")
            continue
        if claim.source not in ("calendar", "register", "corpus"):
            defects.append(f"claim {i} has an unrecognised source '{claim.source}'")
            continue

        m = _SECTION_IN_CITATION.search(claim.citation)
        if not m:
            defects.append(f"claim {i} citation '{claim.citation}' does not name a specific section")
            continue

        cited_section = m.group(1).lower()
        parent = cited_section.split("(")[0]
        if cited_section not in known_sections and parent not in known_sections:
            defects.append(
                f"claim {i} cites section {cited_section}, which does not "
                f"match any section in the corpus or register — possible invented citation"
            )

    return Verdict(passed=len(defects) == 0, defects=defects)