from pathlib import Path

from ingestion.source import LocalFileSource
from ingestion.watcher import SnapshotStore, check_source, run_watch_cycle
from ingestion.impact import find_affected_obligations
from registry.store import RegisterStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DATA = Path(__file__).resolve().parent.parent / "data" / "obligations"


def test_first_seen_is_flagged_but_not_a_diff(tmp_path):
    src = LocalFileSource("mca_circulars", FIXTURES / "mca_circulars_v1.txt")
    store = SnapshotStore(tmp_path)
    event = check_source(src, store)
    assert event is not None
    assert event.is_first_seen is True
    assert event.previous_hash is None


def test_unchanged_content_produces_no_event(tmp_path):
    src = LocalFileSource("mca_circulars", FIXTURES / "mca_circulars_v1.txt")
    store = SnapshotStore(tmp_path)
    check_source(src, store)
    event = check_source(src, store)
    assert event is None


def test_changed_content_produces_a_diff(tmp_path):
    store = SnapshotStore(tmp_path)
    v1 = LocalFileSource("mca_circulars", FIXTURES / "mca_circulars_v1.txt")
    check_source(v1, store)

    v2 = LocalFileSource("mca_circulars", FIXTURES / "mca_circulars_v2.txt")
    event = check_source(v2, store)

    assert event is not None
    assert event.is_first_seen is False
    assert event.previous_hash is not None
    assert "137" in event.diff_preview or "AOC-4" in event.diff_preview


def test_watch_cycle_checks_every_source_once(tmp_path):
    store = SnapshotStore(tmp_path)
    sources = [
        LocalFileSource("a", FIXTURES / "mca_circulars_v1.txt"),
        LocalFileSource("b", FIXTURES / "mca_circulars_v1.txt"),
    ]
    events = run_watch_cycle(sources, store)
    assert len(events) == 2


def test_impact_matcher_flags_the_right_obligation(tmp_path):
    store = SnapshotStore(tmp_path)
    v1 = LocalFileSource("mca_circulars", FIXTURES / "mca_circulars_v1.txt")
    check_source(v1, store)
    v2 = LocalFileSource("mca_circulars", FIXTURES / "mca_circulars_v2.txt")
    event = check_source(v2, store)

    register = RegisterStore(DATA).load_all()
    candidates = find_affected_obligations(event, register.all_latest())

    ids = [c.obligation_id for c in candidates]
    assert "MCA.AOC4.ANNUAL" in ids
    assert "GST.GSTR3B.MONTHLY" not in ids