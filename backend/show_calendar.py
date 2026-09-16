"""
Run me to see the difference with your own eyes:

    python show_calendar.py

Old system: "AOC-4 Filing Acknowledgement" is on file -> status OK, forever.
New system: two dated, unfiled obligations with their derivations shown.
"""
import json
from datetime import date
from pathlib import Path

from domain.obligation import Obligation
from domain.materialise import materialise

DATA = Path(__file__).resolve().parent / "data"
TODAY = date.today()

obligation_path = DATA / "obligations" / "MCA.AOC4.ANNUAL" / "v1.json"
obligation = Obligation(**json.loads(obligation_path.read_text()))
profile = json.loads((DATA / "sample_org.json").read_text())
profile |= {"entity_type": "PRIVATE_LIMITED", "status": "ACTIVE", "entity_id": "SKYLOGIX"}

instances = materialise(
    obligation,
    profile,
    today=TODAY,
    horizon_months=18,
    evidence_periods={"FY2024-25"},   # the one acknowledgement actually on file
)

print(f"\n{profile['org_name']} — {obligation.title}")
print(f"as of {TODAY:%d %b %Y}   ({obligation.act} s.{obligation.section})")
print("=" * 78)

if not instances:
    print("No instances — obligation does not apply to this entity.")

for i in instances:
    flag = "  " if i.status.value == "FILED" else "! "
    print(f"\n{flag}{i.period_label}   due {i.due_date:%d %b %Y}   [{i.status.value}]")
    print(f"    in {i.days_to_due(TODAY)} days")
    print(f"    why: {i.due_date_basis}")

print("\n" + "=" * 78)
open_count = sum(1 for i in instances if i.status.value != "FILED")
print(f"{open_count} open AOC-4 filing(s). The old model reported 0.\n")