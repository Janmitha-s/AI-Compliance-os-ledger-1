from datetime import date
from pathlib import Path
import json

from registry.store import RegisterStore
from corpus.chunker import chunk_statute_text
from corpus.index import CorpusIndex
from agents.tools import Tools
from agents.audit import AuditLog
from agents.retrieval_agent import answer_question, Answer, Claim
from agents.critic import review

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def build_tools() -> Tools:
    register = RegisterStore(DATA / "obligations").load_all()
    raw = (DATA / "corpus" / "companies_act_2013_extract.txt").read_text()
    chunks = chunk_statute_text(raw, act="Companies Act, 2013",
                                 source_url="https://www.incometaxindia.gov.in")
    corpus = CorpusIndex(chunks)
    return Tools(register, corpus, AuditLog())


def skylogix_profile() -> dict:
    raw = json.loads((DATA / "sample_org.json").read_text())
    raw |= {
        "entity_type": "PRIVATE_LIMITED", "status": "ACTIVE", "entity_id": "SKYLOGIX",
        "has_msme_supplier_dues": True,
        "directors": [{"din": "00111111", "name": "A. Rao", "has_active_din": True}],
    }
    return raw


def test_answer_surfaces_a_blocked_dependency_from_the_calendar():
    tools = build_tools()
    answer = answer_question(tools, "What's our compliance status?", skylogix_profile(), date(2026, 9, 15))
    assert answer.grounded
    blocked_claims = [c for c in answer.claims if "BLOCKED" in c.text]
    assert any("MCA.ADT1.ANNUAL" in c.text for c in blocked_claims)


def test_answer_combines_calendar_and_corpus_claims():
    """Full calendar claims are always present (they run regardless of the
    question), so pick a question with a genuine lexical match in the real
    Act text too — "AOC-4"/"AGM" deliberately don't have one (see
    retrieval_agent.py's form-code routing), so this test uses a question
    that actually shares vocabulary with the statute instead."""
    tools = build_tools()
    answer = answer_question(tools, "What disqualifies someone from being a director?",
                              skylogix_profile(), date(2026, 9, 15))
    sources = {c.source for c in answer.claims}
    assert "calendar" in sources
    assert "corpus" in sources

def test_answer_refuses_on_a_genuinely_unanswerable_question():
    tools = build_tools()
    answer = answer_question(tools, "what is the capital gains tax rate on listed equity",
                              {}, date(2026, 9, 15))
    assert answer.grounded is False
    assert answer.refusal_reason


def test_critic_passes_a_genuinely_grounded_answer():
    tools = build_tools()
    answer = answer_question(tools, "When is Form AOC-4 due after the AGM?",
                              skylogix_profile(), date(2026, 9, 15))
    verdict = review(answer, tools.register, tools.corpus)
    assert verdict.passed, verdict.defects


def test_critic_passes_a_correct_refusal():
    tools = build_tools()
    answer = answer_question(tools, "capital gains tax rate", {}, date(2026, 9, 15))
    verdict = review(answer, tools.register, tools.corpus)
    assert verdict.passed


def test_critic_catches_a_claim_with_no_citation():
    tools = build_tools()
    bad = Answer(question="t", claims=[Claim("True.", "corpus", "")], grounded=True)
    verdict = review(bad, tools.register, tools.corpus)
    assert not verdict.passed
    assert any("no citation" in d for d in verdict.defects)


def test_critic_catches_an_invented_section_number():
    tools = build_tools()
    bad = Answer(question="t", claims=[Claim(
        "Section 999 requires annual filing.", "corpus",
        "Companies Act, 2013, s.999 (https://example.gov.in)",
    )], grounded=True)
    verdict = review(bad, tools.register, tools.corpus)
    assert not verdict.passed
    assert any("999" in d for d in verdict.defects)


def test_critic_accepts_a_calendar_sourced_claim():
    tools = build_tools()
    good = Answer(question="t", claims=[Claim(
        "AOC-4 for FY2025-26 is BLOCKED: ADT-1 not filed", "calendar",
        "Companies Act, 2013, s.137(1) (https://example.gov.in)",
    )], grounded=True)
    verdict = review(good, tools.register, tools.corpus)
    assert verdict.passed, verdict.defects