"""
The test that proves the old bug is dead.

Old behaviour: SkyLogix holds one "AOC-4 Filing Acknowledgement" with no
expiry date, so the system reported it compliant on AOC-4 forever.

New behaviour: that acknowledgement covers FY2024-25 only. FY2025-26 and
FY2026-27 are separate, dated, unfiled obligations.
"""
import json
from datetime import date
from pathlib import Path

from domain.obligation import InstanceStatus, Obligation
from domain.materialise import materialise

DATA = Path(__file__).resolve().parent.parent / "data"
TODAY = date(2026, 9, 15)


def load_aoc4() -> Obligation:
    path = DATA / "obligations" / "MCA.AOC4.ANNUAL" / "v1.json"
    return Obligation(**json.loads(path.read_text())) 


def skylogix_profile() -> dict:
    raw = json.loads((DATA / "sample_org.json").read_text())
    # fields the new applicability predicates need but the old schema lacked
    raw["entity_type"] = "PRIVATE_LIMITED"
    raw["status"] = "ACTIVE"
    raw["entity_id"] = "SKYLOGIX"
    return raw


def test_generates_two_future_aoc4_instances():
    """The headline assertion. One filing != permanent compliance."""
    obligation = load_aoc4()
    profile = skylogix_profile()

    instances = materialise(
        obligation,
        profile,
        today=TODAY,
        horizon_months=18,
        evidence_periods={"FY2024-25"},   # the acknowledgement on file
    )

    labels = [i.period_label for i in instances]
    assert "FY2025-26" in labels, "the FY that just closed must appear"
    assert "FY2026-27" in labels, "next year's filing must appear too"

    open_items = [i for i in instances if i.status != InstanceStatus.FILED]
    assert len(open_items) == 2, f"expected 2 open AOC-4 filings, got {labels}"


def test_due_dates_are_correct_and_explained():
    obligation = load_aoc4()
    instances = materialise(obligation, skylogix_profile(), today=TODAY)
    by_period = {i.period_label: i for i in instances}

    # FY2025-26 ends 31 Mar 2026 -> deemed AGM 30 Sep 2026 -> +30d
    assert by_period["FY2025-26"].due_date == date(2026, 10, 30)
    # FY2026-27 ends 31 Mar 2027 -> deemed AGM 30 Sep 2027 -> +30d
    assert by_period["FY2026-27"].due_date == date(2027, 10, 30)

    # every date must carry its own working
    for inst in instances:
        assert "s.137(1)" in inst.due_date_basis


def test_real_agm_date_overrides_the_deemed_one():
    obligation = load_aoc4()
    instances = materialise(
        obligation,
        skylogix_profile(),
        today=TODAY,
        agm_dates={"FY2025-26": date(2026, 8, 12)},
    )
    fy = {i.period_label: i for i in instances}["FY2025-26"]
    assert fy.due_date == date(2026, 9, 11)          # 12 Aug + 30 days
    assert "AGM held 12 Aug 2026" in fy.due_date_basis


def test_evidence_for_one_year_does_not_cover_another():
    """This is the bug, stated as a test."""
    obligation = load_aoc4()
    instances = materialise(
        obligation, skylogix_profile(), today=TODAY,
        evidence_periods={"FY2024-25"},
    )
    fy2526 = {i.period_label: i for i in instances}["FY2025-26"]
    assert fy2526.status != InstanceStatus.FILED


def test_not_applicable_to_an_llp():
    obligation = load_aoc4()
    profile = skylogix_profile() | {"entity_type": "LLP"}
    assert materialise(obligation, profile, today=TODAY) == []


def test_missing_profile_field_is_undetermined_not_false():
    """Silent defaults are how compliance systems under-report."""
    from domain.materialise import is_applicable
    obligation = load_aoc4()
    profile = skylogix_profile()
    del profile["status"]
    verdict, unresolved = is_applicable(obligation, profile)
    assert verdict is None
    assert "status" in unresolved