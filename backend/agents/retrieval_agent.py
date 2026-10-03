"""
The Research/Retrieval Agent. Combines the calendar (deterministic facts),
the register (exact form-code -> section mapping), and the corpus (ranked,
always-cited, allowed-to-refuse free-text search).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from domain.obligation import InstanceStatus
from .tools import Tools

FORM_CODE_TO_OBLIGATION: dict[str, str] = {
    "aoc-4": "MCA.AOC4.ANNUAL", "aoc4": "MCA.AOC4.ANNUAL",
    "adt-1": "MCA.ADT1.ANNUAL", "adt1": "MCA.ADT1.ANNUAL",
    "mgt-7": "MCA.MGT7.ANNUAL", "mgt7": "MCA.MGT7.ANNUAL",
    "dir-3 kyc": "MCA.DIR3KYC.ANNUAL", "dir3 kyc": "MCA.DIR3KYC.ANNUAL",
    "dir-3kyc": "MCA.DIR3KYC.ANNUAL", "dir3kyc": "MCA.DIR3KYC.ANNUAL",
    "dpt-3": "MCA.DPT3.ANNUAL", "dpt3": "MCA.DPT3.ANNUAL",
    "msme-1": "MCA.MSME1.HALFYEARLY", "msme1": "MCA.MSME1.HALFYEARLY",
}


@dataclass
class Claim:
    text: str
    source: str          # "calendar" | "register" | "corpus"
    citation: str


@dataclass
class Answer:
    question: str
    claims: list[Claim] = field(default_factory=list)
    grounded: bool = True
    refusal_reason: str = ""


def _resolve_form_codes(tools: Tools, question: str, as_of: date) -> list[Claim]:
    q = question.lower()
    claims: list[Claim] = []
    matched_ids = {ob_id for code, ob_id in FORM_CODE_TO_OBLIGATION.items() if code in q}
    for obligation_id in matched_ids:
        ob = tools.register.as_of(obligation_id, as_of)
        if ob is None:
            continue
        claims.append(Claim(
            text=f"{ob.title} — {ob.act}, s.{ob.section}, filed under {ob.authority}.",
            source="register",
            citation=f"{ob.act}, s.{ob.section} ({ob.source_url})",
        ))
    return claims


def answer_question(tools: Tools, question: str, profile: dict, as_of: date) -> Answer:
    calendar = tools.full_calendar(profile, as_of)
    claims: list[Claim] = []
    has_real_signal = False

    for inst in calendar.instances:
        ob = calendar.obligations_by_id[inst.obligation_id]
        citation = f"{ob.act}, s.{ob.section} ({ob.source_url})"
        who = f" (director {inst.subject_id})" if ob.subject == "DIRECTOR" else ""

        if inst.status == InstanceStatus.BLOCKED:
            has_real_signal = True
            claims.append(Claim(
                text=f"{ob.title}{who} for {inst.period_label} is BLOCKED: {inst.blocked_reason}",
                source="calendar", citation=citation,
            ))
        elif inst.status in (InstanceStatus.NOT_STARTED, InstanceStatus.LATE):
            has_real_signal = True
            urgency = "OVERDUE" if inst.status == InstanceStatus.LATE else "due"
            claims.append(Claim(
                text=f"{ob.title}{who} for {inst.period_label} is {urgency} "
                     f"{inst.due_date:%d %b %Y} ({inst.due_date_basis})",
                source="calendar", citation=citation,
            ))

    for u in calendar.undetermined:
        claims.append(Claim(
            text=f"Cannot determine whether '{u.title}' applies — "
                 f"missing profile field(s): {', '.join(u.unresolved_fields)}.",
            source="calendar", citation=u.citation,
        ))

    form_code_claims = _resolve_form_codes(tools, question, as_of)
    if form_code_claims:
        has_real_signal = True
        claims.extend(form_code_claims)

    corpus_result = tools.corpus_search(question)
    if corpus_result["grounded"]:
        has_real_signal = True
        for item in corpus_result["answer_material"]:
            claims.append(Claim(text=item["text"][:300], source="corpus", citation=item["citation"]))

    if not has_real_signal:
        return Answer(
            question=question, claims=[], grounded=False,
            refusal_reason=corpus_result.get("message", "No grounded material found for this question."),
        )

    return Answer(question=question, claims=claims, grounded=True)