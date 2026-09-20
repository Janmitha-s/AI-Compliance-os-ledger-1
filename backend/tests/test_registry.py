from datetime import date
from pathlib import Path

import pytest

from registry.store import RegisterStore, ProvenanceError

DATA = Path(__file__).resolve().parent.parent / "data" / "obligations"


def test_loads_all_valid_obligations():
    store = RegisterStore(DATA).load_all()
    assert "MCA.AOC4.ANNUAL" in store.all_ids()
    assert "GST.GSTR3B.MONTHLY" in store.all_ids()
    assert "MCA.DIR3KYC.ANNUAL" in store.all_ids()


def test_version_resolution_by_date():
    store = RegisterStore(DATA).load_all()
    before = store.as_of("MCA.AOC4.ANNUAL", date(2026, 9, 15))
    after = store.as_of("MCA.AOC4.ANNUAL", date(2027, 6, 1))
    assert before.version == 1
    assert after.version == 2


def test_as_of_before_anything_existed_returns_none():
    store = RegisterStore(DATA).load_all()
    assert store.as_of("MCA.AOC4.ANNUAL", date(2000, 1, 1)) is None


def test_latest_ignores_date():
    store = RegisterStore(DATA).load_all()
    assert store.latest("MCA.AOC4.ANNUAL").version == 2


def test_unreviewed_queue_contains_drafts_only():
    store = RegisterStore(DATA).load_all()
    drafts = {o.obligation_id: o.version for o in store.unreviewed()}
    assert drafts.get("GST.GSTR3B.MONTHLY") == 1
    assert "MCA.MGT7.ANNUAL" not in drafts  # this one is HUMAN_VERIFIED


def test_rejects_obligation_missing_provenance(tmp_path):
    bad = tmp_path / "BAD.ONE" / "v1.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("""{
        "obligation_id": "BAD.ONE",
        "version": 1,
        "title": "Missing its citation",
        "authority": "Nobody",
        "applicability": [],
        "periodicity": {"type": "ANNUAL", "anchor": "FY_END", "offset_days": 0}
    }""")
    with pytest.raises(ProvenanceError) as exc:
        RegisterStore(tmp_path).load_all()
    assert "missing provenance" in str(exc.value)


def test_rejects_duplicate_version(tmp_path):
    folder = tmp_path / "DUP.ONE"
    folder.mkdir(parents=True)
    body = """{
        "obligation_id": "DUP.ONE", "version": 1,
        "effective_from": "2020-01-01", "title": "t", "authority": "a",
        "act": "Some Act", "section": "1", "source_url": "https://example.gov.in",
        "applicability": [],
        "periodicity": {"type": "ANNUAL", "anchor": "FY_END", "offset_days": 0}
    }"""
    (folder / "v1.json").write_text(body)
    (folder / "v1_typo.json").write_text(body)
    with pytest.raises(ProvenanceError) as exc:
        RegisterStore(tmp_path).load_all()
    assert "duplicate version" in str(exc.value)