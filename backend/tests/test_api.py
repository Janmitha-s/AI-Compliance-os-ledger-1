import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

DATA = Path(__file__).resolve().parent.parent / "data"


def skylogix_profile() -> dict:
    raw = json.loads((DATA / "sample_org.json").read_text())
    raw |= {
        "entity_type": "PRIVATE_LIMITED", "status": "ACTIVE", "entity_id": "SKYLOGIX",
        "has_msme_supplier_dues": True,
        "directors": [{"din": "00111111", "name": "A. Rao", "has_active_din": True}],
    }
    return raw


def test_health_reports_the_register_is_loaded():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["obligations_loaded"] >= 6


def test_obligations_lists_every_loaded_obligation():
    r = client.get("/obligations")
    assert r.status_code == 200
    ids = {o["obligation_id"] for o in r.json()}
    assert "MCA.AOC4.ANNUAL" in ids
    assert "MCA.DIR3KYC.ANNUAL" in ids


def test_plain_question_completes_in_one_call_no_thread_needed_again():
    r = client.post("/assess", json={
        "goal": "When is Form AOC-4 due after the AGM?",
        "profile": skylogix_profile(),
        "as_of": "2026-09-15",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["final_report"]["critic_passed"] is True


def test_blocked_filing_completes_without_ever_pending_approval():
    r = client.post("/assess", json={
        "goal": "Prepare the AOC-4 filing",
        "profile": skylogix_profile(),
        "obligation_id": "MCA.AOC4.ANNUAL",
        "as_of": "2026-09-15",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"           # never pending_approval
    assert body["final_report"]["filing_status"] == "CANNOT PREPARE"


def test_ready_filing_pends_then_resumes_via_two_http_calls():
    start = client.post("/assess", json={
        "goal": "Prepare the ADT-1 filing",
        "profile": skylogix_profile(),
        "obligation_id": "MCA.ADT1.ANNUAL",
        "as_of": "2026-09-15",
    })
    assert start.status_code == 200
    body = start.json()
    assert body["status"] == "pending_approval"
    assert body["pending_approval"]["obligation_id"] == "MCA.ADT1.ANNUAL"
    thread_id = body["thread_id"]

    resumed = client.post(f"/assess/{thread_id}/decision", json={"approved": True})
    assert resumed.status_code == 200
    final = resumed.json()
    assert final["status"] == "completed"
    assert final["final_report"]["filing_approved"] is True
    assert final["final_report"]["filing_status"].startswith("READY")


def test_resuming_an_unknown_thread_id_returns_404():
    r = client.post("/assess/does-not-exist/decision", json={"approved": True})
    assert r.status_code == 404