import json
from datetime import date
from pathlib import Path

from langgraph.types import Command

from registry.store import RegisterStore
from corpus.chunker import chunk_statute_text
from corpus.index import CorpusIndex
from agents.audit import AuditLog
from graph.workflow import build_graph

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def build_app():
    register = RegisterStore(DATA / "obligations").load_all()
    raw = (DATA / "corpus" / "companies_act_2013_extract.txt").read_text()
    chunks = chunk_statute_text(raw, act="Companies Act, 2013",
                                 source_url="https://www.incometaxindia.gov.in")
    corpus = CorpusIndex(chunks)
    audit = AuditLog()
    return build_graph(register, corpus, audit), audit


def skylogix_profile() -> dict:
    raw = json.loads((DATA / "sample_org.json").read_text())
    raw |= {
        "entity_type": "PRIVATE_LIMITED", "status": "ACTIVE", "entity_id": "SKYLOGIX",
        "has_msme_supplier_dues": True,
        "directors": [{"din": "00111111", "name": "A. Rao", "has_active_din": True}],
    }
    return raw


def test_plain_question_never_touches_the_human_gate():
    app, audit = build_app()
    cfg = {"configurable": {"thread_id": "q1"}}
    result = app.invoke({
        "goal": "When is Form AOC-4 due after the AGM?",
        "profile": skylogix_profile(), "as_of": date(2026, 9, 15),
    }, config=cfg)

    assert "__interrupt__" not in result
    assert result["final_report"]["critic_passed"] is True
    assert not audit.for_actor("human")


def test_assessment_goal_surfaces_the_blocked_dependency():
    app, _ = build_app()
    cfg = {"configurable": {"thread_id": "q2"}}
    result = app.invoke({
        "goal": "Assess compliance posture for SkyLogix",
        "profile": skylogix_profile(), "as_of": date(2026, 9, 15),
    }, config=cfg)
    report = result["final_report"]
    assert report["critic_passed"] is True
    assert any("BLOCKED" in c["text"] for c in report["answer"]["claims"])


def test_blocked_filing_never_reaches_the_human_gate():
    app, audit = build_app()
    cfg = {"configurable": {"thread_id": "q3"}}
    result = app.invoke({
        "goal": "Prepare the AOC-4 filing for SkyLogix",
        "profile": skylogix_profile(), "obligation_id": "MCA.AOC4.ANNUAL",
        "as_of": date(2026, 9, 15),
    }, config=cfg)

    assert "__interrupt__" not in result
    report = result["final_report"]
    assert report["filing_status"] == "CANNOT PREPARE"
    assert "MCA.ADT1.ANNUAL" in report["filing_refusal_reason"]
    assert not audit.for_actor("human")


def test_ready_filing_pauses_at_the_human_gate():
    app, _ = build_app()
    cfg = {"configurable": {"thread_id": "q4"}}
    result = app.invoke({
        "goal": "Prepare the ADT-1 filing for SkyLogix",
        "profile": skylogix_profile(), "obligation_id": "MCA.ADT1.ANNUAL",
        "as_of": date(2026, 9, 15),
    }, config=cfg)

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["obligation_id"] == "MCA.ADT1.ANNUAL"
    assert "final_report" not in result


def test_ready_filing_resumes_and_finishes_after_approval():
    app, audit = build_app()
    cfg = {"configurable": {"thread_id": "q5"}}
    app.invoke({
        "goal": "Prepare the ADT-1 filing for SkyLogix",
        "profile": skylogix_profile(), "obligation_id": "MCA.ADT1.ANNUAL",
        "as_of": date(2026, 9, 15),
    }, config=cfg)

    result = app.invoke(Command(resume=True), config=cfg)
    report = result["final_report"]
    assert report["filing_approved"] is True
    assert report["filing_status"].startswith("READY")
    assert len(audit.for_actor("human")) == 1


def test_ready_filing_resumes_with_rejection_stays_blocked():
    app, _ = build_app()
    cfg = {"configurable": {"thread_id": "q6"}}
    app.invoke({
        "goal": "Prepare the ADT-1 filing for SkyLogix",
        "profile": skylogix_profile(), "obligation_id": "MCA.ADT1.ANNUAL",
        "as_of": date(2026, 9, 15),
    }, config=cfg)

    result = app.invoke(Command(resume=False), config=cfg)
    report = result["final_report"]
    assert report["filing_approved"] is False
    assert report["filing_status"].startswith("BLOCKED")


def test_director_subject_filing_without_din_never_reaches_the_human_gate():
    app, audit = build_app()
    cfg = {"configurable": {"thread_id": "q7"}}
    result = app.invoke({
        "goal": "Prepare the DIR-3 KYC filing",
        "profile": skylogix_profile(), "obligation_id": "MCA.DIR3KYC.ANNUAL",
        "as_of": date(2026, 9, 15),
    }, config=cfg)

    assert "__interrupt__" not in result
    report = result["final_report"]
    assert report["filing_status"] == "CANNOT PREPARE"
    assert "director" in report["filing_refusal_reason"].lower()
    assert not audit.for_actor("human")


def test_director_subject_filing_with_din_reaches_the_gate():
    app, _ = build_app()
    cfg = {"configurable": {"thread_id": "q8"}}
    result = app.invoke({
        "goal": "Prepare the DIR-3 KYC filing",
        "profile": skylogix_profile(), "obligation_id": "MCA.DIR3KYC.ANNUAL",
        "subject_id": "00111111", "as_of": date(2026, 9, 15),
    }, config=cfg)

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["subject_id"] == "00111111"


def test_a_run_with_no_grounded_material_is_flagged_needs_review():
    app, _ = build_app()
    cfg = {"configurable": {"thread_id": "q9"}}
    result = app.invoke({
        "goal": "what is the capital gains tax rate on listed equity",
        "profile": {}, "as_of": date(2026, 9, 15),
    }, config=cfg)
    report = result["final_report"]
    assert report["answer"]["grounded"] is False
    assert report["critic_passed"] is True