"""
The tool layer. Agents never touch the register, the corpus index, or
`materialise()` directly — they call these methods, and every call is
logged to the AuditLog. If a tool isn't exposed here, no agent can do it.
`filing_prep` refuses outright (never producing a draft) for a blocked
dependency or a director-subject obligation with no director specified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from registry.store import RegisterStore
from domain.materialise import materialise, is_applicable, apply_dependencies
from domain.obligation import ObligationInstance, InstanceStatus, Obligation
from corpus.index import CorpusIndex, grounded_answer

from .audit import AuditLog


@dataclass
class ApplicabilityResult:
    obligation_id: str
    title: str
    verdict: Optional[bool]
    unresolved_fields: list[str]
    citation: str


@dataclass
class CalendarResult:
    instances: list[ObligationInstance]
    undetermined: list[ApplicabilityResult]
    obligations_by_id: dict[str, Obligation]


@dataclass
class FilingPrepResult:
    ready: bool
    instance: Optional[ObligationInstance]
    checklist: list[str] = field(default_factory=list)
    requires_approval: bool = True
    refusal_reason: str = ""


class Tools:
    def __init__(self, register: RegisterStore, corpus: CorpusIndex, audit: AuditLog):
        self.register = register
        self.corpus = corpus
        self.audit = audit

    def register_query(self, profile: dict, as_of: date) -> list[ApplicabilityResult]:
        results = []
        for obligation_id in self.register.all_ids():
            ob = self.register.as_of(obligation_id, as_of)
            if ob is None:
                continue
            verdict, unresolved = is_applicable(ob, profile)
            results.append(ApplicabilityResult(
                obligation_id=ob.obligation_id, title=ob.title, verdict=verdict,
                unresolved_fields=unresolved,
                citation=f"{ob.act}, s.{ob.section} ({ob.source_url})",
            ))
        self.audit.record("tool:register_query", "tool_call", profile, results,
                           {"as_of": as_of.isoformat()})
        return results

    def materialise_calendar(
        self, obligation_id: str, profile: dict, today: date, horizon_months: int = 18,
        **kwargs,
    ) -> list[ObligationInstance]:
        ob = self.register.as_of(obligation_id, today)
        if ob is None:
            self.audit.record("tool:materialise_calendar", "tool_call",
                               {"obligation_id": obligation_id}, [],
                               {"reason": "no version of this obligation was in force on `today`"})
            return []
        instances = materialise(ob, profile, today, horizon_months=horizon_months, **kwargs)
        self.audit.record("tool:materialise_calendar", "tool_call",
                           {"obligation_id": obligation_id, "today": today.isoformat()},
                           [i.model_dump(mode="json") for i in instances])
        return instances

    def full_calendar(
        self, profile: dict, today: date, horizon_months: int = 18,
        evidence_by_obligation: Optional[dict[str, set[str]]] = None,
        agm_dates: Optional[dict[str, date]] = None,
    ) -> CalendarResult:
        evidence_by_obligation = evidence_by_obligation or {}
        applicability = self.register_query(profile, today)

        instances_by_obligation: dict[str, list[ObligationInstance]] = {}
        obligations_by_id: dict[str, Obligation] = {}
        undetermined: list[ApplicabilityResult] = []

        for r in applicability:
            ob = self.register.as_of(r.obligation_id, today)
            if ob is None:
                continue

            if ob.subject == "DIRECTOR":
                if not profile.get("directors"):
                    undetermined.append(ApplicabilityResult(
                        obligation_id=ob.obligation_id, title=ob.title, verdict=None,
                        unresolved_fields=["directors"], citation=r.citation,
                    ))
                    continue
                obligations_by_id[r.obligation_id] = ob
                instances_by_obligation[r.obligation_id] = materialise(
                    ob, profile, today, horizon_months=horizon_months,
                    evidence_periods=evidence_by_obligation.get(r.obligation_id),
                    agm_dates=agm_dates,
                )
                continue

            if r.verdict is None:
                undetermined.append(r)
                continue
            if r.verdict is False:
                continue
            obligations_by_id[r.obligation_id] = ob
            instances_by_obligation[r.obligation_id] = materialise(
                ob, profile, today, horizon_months=horizon_months,
                evidence_periods=evidence_by_obligation.get(r.obligation_id),
                agm_dates=agm_dates,
            )

        apply_dependencies(instances_by_obligation, obligations_by_id)

        flat = [inst for insts in instances_by_obligation.values() for inst in insts]
        flat.sort(key=lambda i: i.due_date)

        self.audit.record("tool:full_calendar", "tool_call", profile,
                           [i.model_dump(mode="json") for i in flat],
                           {"undetermined_count": len(undetermined)})
        return CalendarResult(instances=flat, undetermined=undetermined, obligations_by_id=obligations_by_id)

    def corpus_search(self, question: str, top_k: int = 3, min_score: float = 1.5) -> dict:
        result = grounded_answer(self.corpus, question, top_k=top_k, min_score=min_score)
        self.audit.record("tool:corpus_search", "tool_call", {"question": question}, result)
        return result

    def filing_prep(
        self, calendar: CalendarResult, obligation_id: str, subject_id: Optional[str] = None,
    ) -> FilingPrepResult:
        ob = calendar.obligations_by_id.get(obligation_id) or self.register.as_of(obligation_id, date.today())
        if ob is None:
            return FilingPrepResult(ready=False, instance=None,
                                     refusal_reason=f"{obligation_id} is not in the register")

        if ob.subject == "DIRECTOR" and not subject_id:
            return FilingPrepResult(
                ready=False, instance=None,
                refusal_reason=(
                    f"{obligation_id} attaches to individual directors, not the company. "
                    f"Specify which director (DIN) before a filing can be prepared."
                ),
            )

        candidates = [
            i for i in calendar.instances
            if i.obligation_id == obligation_id
            and (subject_id is None or i.subject_id == subject_id)
        ]
        candidates.sort(key=lambda i: i.due_date)

        actionable = [i for i in candidates if i.status in (InstanceStatus.NOT_STARTED, InstanceStatus.LATE)]
        blocked = [i for i in candidates if i.status == InstanceStatus.BLOCKED]

        if not actionable and blocked:
            b = blocked[0]
            self.audit.record("tool:filing_prep", "tool_call",
                               {"obligation_id": obligation_id, "subject_id": subject_id},
                               {"ready": False}, {"reason": b.blocked_reason})
            return FilingPrepResult(
                ready=False, instance=b,
                refusal_reason=f"Blocked for {b.period_label}: {b.blocked_reason}",
            )

        if not actionable:
            return FilingPrepResult(ready=False, instance=None,
                                     refusal_reason="Nothing outstanding to prepare for this obligation.")

        instance = actionable[0]
        checklist = [
            f"Confirm period {instance.period_label} evidence: {', '.join(ob.evidence_kinds)}",
            f"Confirm due date basis: {instance.due_date_basis}",
            "Route to authorised signatory for review",
            "Human approval required before this can be marked ready-to-file",
        ]
        result = FilingPrepResult(ready=True, instance=instance, checklist=checklist)
        self.audit.record("tool:filing_prep", "tool_call",
                           {"obligation_id": obligation_id, "subject_id": subject_id,
                            "period": instance.period_label},
                           {"ready": True})
        return result