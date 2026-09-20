"""
One test per modelling question from the step-1 roadmap, plus one test per
new obligation loading and producing sane output. TODAY is fixed so every
date assertion is exact, not "roughly right."
"""
import json
from datetime import date
from pathlib import Path

from domain.obligation import InstanceStatus, Obligation
from domain.materialise import materialise, apply_dependencies

DATA = Path(__file__).resolve().parent.parent / "data"
TODAY = date(2026, 9, 15)


def load(obligation_id: str, version: str = "v1") -> Obligation:
    path = DATA / "obligations" / obligation_id / f"{version}.json"
    return Obligation(**json.loads(path.read_text()))


def skylogix_profile() -> dict:
    raw = json.loads((DATA / "sample_org.json").read_text())
    raw |= {
        "entity_type": "PRIVATE_LIMITED",
        "status": "ACTIVE",
        "entity_id": "SKYLOGIX",
        "has_msme_supplier_dues": True,
        "directors": [
            {"din": "00111111", "name": "A. Rao", "has_active_din": True},
            {"din": "00222222", "name": "B. Iyer", "has_active_din": True},
            {"din": "00333333", "name": "C. Menon", "has_active_din": False},  # resigned
        ],
    }
    return raw


# ---------------------------------------------------------------- ADT-1


def test_adt1_uses_15_day_offset_not_30():
    obligation = load("MCA.ADT1.ANNUAL")
    instances = materialise(obligation, skylogix_profile(), today=TODAY)
    fy2526 = next(i for i in instances if i.period_label == "FY2025-26")
    # deemed AGM 30 Sep 2026 + 15 days
    assert fy2526.due_date == date(2026, 10, 15)


# ---------------------------------------------------------------- MGT-7


def test_mgt7_uses_60_day_offset():
    obligation = load("MCA.MGT7.ANNUAL")
    instances = materialise(obligation, skylogix_profile(), today=TODAY)
    fy2526 = next(i for i in instances if i.period_label == "FY2025-26")
    assert fy2526.due_date == date(2026, 11, 29)  # 30 Sep 2026 + 60 days


# ---------------------------------------------------------------- DIR-3 KYC (subject=DIRECTOR)


def test_dir3kyc_generates_one_instance_per_active_director_not_per_company():
    obligation = load("MCA.DIR3KYC.ANNUAL")
    instances = materialise(obligation, skylogix_profile(), today=TODAY, horizon_months=6)
    subject_ids = {i.subject_id for i in instances}
    # two active directors -> both appear; the resigned one does not
    assert subject_ids == {"00111111", "00222222"}


def test_dir3kyc_due_date_is_fixed_30_september_every_year():
    obligation = load("MCA.DIR3KYC.ANNUAL")
    instances = materialise(obligation, skylogix_profile(), today=TODAY, horizon_months=18)
    one_directors_instances = [i for i in instances if i.subject_id == "00111111"]
    due_dates = sorted(i.due_date for i in one_directors_instances)
    assert date(2026, 9, 30) in due_dates
    assert date(2027, 9, 30) in due_dates


def test_dir3kyc_evidence_for_one_director_does_not_mark_another_filed():
    obligation = load("MCA.DIR3KYC.ANNUAL")
    instances = materialise(
        obligation, skylogix_profile(), today=TODAY, horizon_months=6,
        evidence_periods={"00111111:FY2025-26"},
    )
    filed = {i.subject_id: i.status for i in instances if i.period_label == "FY2025-26"}
    assert filed["00111111"] == InstanceStatus.FILED
    assert filed["00222222"] != InstanceStatus.FILED


# ---------------------------------------------------------------- DPT-3 (FIXED_DATE)


def test_dpt3_due_date_is_30_june_independent_of_agm():
    obligation = load("MCA.DPT3.ANNUAL")
    # even with a late/unusual AGM date recorded, DPT-3 doesn't care
    instances = materialise(
        obligation, skylogix_profile(), today=TODAY,
        agm_dates={"FY2025-26": date(2027, 1, 1)},  # deliberately irrelevant
    )
    fy2526 = next(i for i in instances if i.period_label == "FY2025-26")
    assert fy2526.due_date == date(2026, 6, 30)
    assert "Fixed date" in fy2526.due_date_basis


# ---------------------------------------------------------------- MSME-1 (HALF_YEARLY)


def test_msme1_produces_two_periods_per_financial_year():
    obligation = load("MCA.MSME1.HALFYEARLY")
    instances = materialise(obligation, skylogix_profile(), today=TODAY, horizon_months=12)
    labels = {i.period_label for i in instances}
    assert "FY2025-26-H1" in labels
    assert "FY2025-26-H2" in labels


def test_msme1_h1_due_date_is_31_october():
    obligation = load("MCA.MSME1.HALFYEARLY")
    instances = materialise(obligation, skylogix_profile(), today=TODAY, horizon_months=12)
    h1 = next(i for i in instances if i.period_label == "FY2025-26-H1")
    assert h1.period_start == date(2025, 4, 1)
    assert h1.period_end == date(2025, 9, 30)
    assert h1.due_date == date(2025, 10, 31)


def test_msme1_not_applicable_when_no_msme_supplier_dues():
    obligation = load("MCA.MSME1.HALFYEARLY")
    profile = skylogix_profile() | {"has_msme_supplier_dues": False}
    assert materialise(obligation, profile, today=TODAY) == []


# ---------------------------------------------------------------- dependencies (AOC-4 <- ADT-1)


def test_aoc4_is_blocked_when_adt1_not_yet_filed_for_same_period():
    aoc4 = load("MCA.AOC4.ANNUAL")
    adt1 = load("MCA.ADT1.ANNUAL")
    profile = skylogix_profile()

    aoc4_instances = materialise(aoc4, profile, today=TODAY)          # nothing filed
    adt1_instances = materialise(adt1, profile, today=TODAY)          # nothing filed either

    by_obligation = {"MCA.AOC4.ANNUAL": aoc4_instances, "MCA.ADT1.ANNUAL": adt1_instances}
    by_id = {"MCA.AOC4.ANNUAL": aoc4, "MCA.ADT1.ANNUAL": adt1}
    apply_dependencies(by_obligation, by_id)

    fy2526 = next(i for i in aoc4_instances if i.period_label == "FY2025-26")
    assert fy2526.status == InstanceStatus.BLOCKED
    assert "MCA.ADT1.ANNUAL" in fy2526.blocked_reason


def test_aoc4_is_not_blocked_once_adt1_is_filed_for_that_period():
    aoc4 = load("MCA.AOC4.ANNUAL")
    adt1 = load("MCA.ADT1.ANNUAL")
    profile = skylogix_profile()

    aoc4_instances = materialise(aoc4, profile, today=TODAY)
    adt1_instances = materialise(
        adt1, profile, today=TODAY,
        evidence_periods={"FY2025-26"},   # ADT-1 already filed for this FY
    )

    by_obligation = {"MCA.AOC4.ANNUAL": aoc4_instances, "MCA.ADT1.ANNUAL": adt1_instances}
    by_id = {"MCA.AOC4.ANNUAL": aoc4, "MCA.ADT1.ANNUAL": adt1}
    apply_dependencies(by_obligation, by_id)

    fy2526 = next(i for i in aoc4_instances if i.period_label == "FY2025-26")
    assert fy2526.status != InstanceStatus.BLOCKED


def test_dependency_check_does_not_touch_the_due_date():
    """The statute doesn't move AOC-4's deadline because ADT-1 is late."""
    aoc4 = load("MCA.AOC4.ANNUAL")
    adt1 = load("MCA.ADT1.ANNUAL")
    profile = skylogix_profile()

    aoc4_instances = materialise(aoc4, profile, today=TODAY)
    due_before = next(i for i in aoc4_instances if i.period_label == "FY2025-26").due_date

    adt1_instances = materialise(adt1, profile, today=TODAY)
    apply_dependencies(
        {"MCA.AOC4.ANNUAL": aoc4_instances, "MCA.ADT1.ANNUAL": adt1_instances},
        {"MCA.AOC4.ANNUAL": aoc4, "MCA.ADT1.ANNUAL": adt1},
    )
    due_after = next(i for i in aoc4_instances if i.period_label == "FY2025-26").due_date
    assert due_before == due_after