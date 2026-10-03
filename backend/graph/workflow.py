"""
The graph: START -> plan -> execute -> [human_gate only if a READY filing
draft exists] -> critic -> report -> END.

The human gate only fires for a genuinely ready draft. If filing_prep
refused — blocked on a dependency, or a director-subject obligation with
no DIN — there is nothing to approve, and routing that to a human anyway
would either force a pointless rejection or tempt approval of something
that structurally cannot be filed yet.
"""
from __future__ import annotations

from datetime import date

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from registry.store import RegisterStore
from corpus.index import CorpusIndex
from domain.obligation import InstanceStatus
from agents.audit import AuditLog
from agents.tools import Tools
from agents.planner import build_plan
from agents.retrieval_agent import Answer, Claim
from agents.critic import review

from .state import ComplianceState


def build_graph(register: RegisterStore, corpus: CorpusIndex, audit: AuditLog):
    tools = Tools(register, corpus, audit)

    def plan_node(state: ComplianceState) -> dict:
        plan = build_plan(state["goal"], state.get("obligation_id"), state.get("subject_id"))
        audit.record("planner", "plan", state["goal"],
                      [s.kind for s in plan.steps], {"planner": plan.planner})
        return {"plan_steps": [{"kind": s.kind, "args": s.args, "reason": s.reason} for s in plan.steps]}

    def execute_node(state: ComplianceState) -> dict:
        result: dict = {}
        as_of = state.get("as_of", date.today())
        answer_claims: list[Claim] = []
        calendar = None

        for step in state["plan_steps"]:
            kind = step["kind"]

            if kind == "full_calendar":
                calendar = tools.full_calendar(state["profile"], as_of)
                result["instances"] = [i.model_dump(mode="json") for i in calendar.instances]
                result["undetermined"] = [
                    {"obligation_id": u.obligation_id, "title": u.title,
                     "unresolved_fields": u.unresolved_fields, "citation": u.citation}
                    for u in calendar.undetermined
                ]
                for inst in calendar.instances:
                    ob = calendar.obligations_by_id[inst.obligation_id]
                    citation = f"{ob.act}, s.{ob.section} ({ob.source_url})"
                    who = f" (director {inst.subject_id})" if ob.subject == "DIRECTOR" else ""
                    if inst.status == InstanceStatus.BLOCKED:
                        answer_claims.append(Claim(
                            f"{ob.title}{who} for {inst.period_label} is BLOCKED: {inst.blocked_reason}",
                            "calendar", citation))
                    elif inst.status in (InstanceStatus.NOT_STARTED, InstanceStatus.LATE):
                        urgency = "OVERDUE" if inst.status == InstanceStatus.LATE else "due"
                        answer_claims.append(Claim(
                            f"{ob.title}{who} for {inst.period_label} is {urgency} "
                            f"{inst.due_date:%d %b %Y} ({inst.due_date_basis})",
                            "calendar", citation))
                for u in calendar.undetermined:
                    answer_claims.append(Claim(
                        f"Cannot determine whether '{u.title}' applies — "
                        f"missing profile field(s): {', '.join(u.unresolved_fields)}.",
                        "calendar", u.citation))

            elif kind == "corpus_search":
                corpus_result = tools.corpus_search(step["args"]["question"])
                if corpus_result["grounded"]:
                    for item in corpus_result["answer_material"]:
                        answer_claims.append(Claim(item["text"][:300], "corpus", item["citation"]))

            elif kind == "filing_prep":
                if calendar is None:
                    calendar = tools.full_calendar(state["profile"], as_of)
                prep = tools.filing_prep(
                    calendar, step["args"]["obligation_id"], step["args"].get("subject_id"),
                )
                if prep.ready:
                    result["filing_draft"] = {
                        "obligation_id": prep.instance.obligation_id,
                        "subject_id": prep.instance.subject_id,
                        "period_label": prep.instance.period_label,
                        "due_date": prep.instance.due_date.isoformat(),
                        "checklist": prep.checklist,
                        "requires_approval": prep.requires_approval,
                    }
                else:
                    result["filing_draft"] = None
                    result["filing_refusal_reason"] = prep.refusal_reason

        answer = Answer(
            question=state["goal"], claims=answer_claims,
            grounded=bool(answer_claims),
            refusal_reason="" if answer_claims else "no grounded material found for this goal",
        )
        result["answer"] = {
            "question": answer.question, "grounded": answer.grounded,
            "refusal_reason": answer.refusal_reason,
            "claims": [{"text": c.text, "source": c.source, "citation": c.citation} for c in answer.claims],
        }
        return result

    def human_gate_node(state: ComplianceState) -> dict:
        draft = state["filing_draft"]
        decision = interrupt({
            "question": "Approve this filing draft for human sign-off?",
            "obligation_id": draft["obligation_id"],
            "subject_id": draft["subject_id"],
            "period_label": draft["period_label"],
            "due_date": draft["due_date"],
            "checklist": draft["checklist"],
        })
        audit.record("human", "approval", draft, decision)
        return {"approved": bool(decision)}

    def critic_node(state: ComplianceState) -> dict:
        answer = Answer(
            question=state["answer"]["question"],
            grounded=state["answer"]["grounded"],
            refusal_reason=state["answer"]["refusal_reason"],
            claims=[Claim(**c) for c in state["answer"]["claims"]],
        )
        verdict = review(answer, register, corpus)
        audit.record("critic", "verdict", state["answer"], verdict.passed, {"defects": verdict.defects})
        return {"critic_passed": verdict.passed, "critic_defects": verdict.defects}

    def report_node(state: ComplianceState) -> dict:
        report = {
            "goal": state["goal"],
            "instances": state.get("instances", []),
            "undetermined": state.get("undetermined", []),
            "answer": state["answer"],
            "critic_passed": state["critic_passed"],
            "critic_defects": state.get("critic_defects", []),
        }
        if "filing_draft" in state:
            if state["filing_draft"]:
                report["filing_draft"] = state["filing_draft"]
                report["filing_approved"] = state.get("approved", False)
                report["filing_status"] = (
                    "READY — human approved" if state.get("approved")
                    else "BLOCKED — awaiting human approval"
                )
            else:
                report["filing_status"] = "CANNOT PREPARE"
                report["filing_refusal_reason"] = state.get("filing_refusal_reason", "")
        if not state["critic_passed"]:
            report["status"] = "NEEDS_HUMAN_REVIEW"
        return {"final_report": report}

    def route_after_execute(state: ComplianceState) -> str:
        return "human_gate" if state.get("filing_draft") else "critic"

    graph = StateGraph(ComplianceState)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("critic", critic_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "execute")
    graph.add_conditional_edges("execute", route_after_execute, {
        "human_gate": "human_gate", "critic": "critic",
    })
    graph.add_edge("human_gate", "critic")
    graph.add_edge("critic", "report")
    graph.add_edge("report", END)

    return graph.compile(checkpointer=MemorySaver())