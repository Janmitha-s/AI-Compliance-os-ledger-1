from datetime import date
from pathlib import Path

from registry.store import RegisterStore
from ingestion.source import LocalFileSource
from ingestion.watcher import SnapshotStore, check_source
from ingestion.impact import find_affected_obligations
from corpus.chunker import chunk_statute_text
from corpus.index import CorpusIndex, grounded_answer

ROOT = Path(__file__).resolve().parent

print("\n1. REGISTER")
print("=" * 70)
register = RegisterStore(ROOT / "data" / "obligations").load_all()
print(f"loaded {len(register.all_ids())} obligations: {register.all_ids()}")
print(f"{len(register.unreviewed())} still DRAFT, awaiting CS/CA review")

before = register.as_of("MCA.AOC4.ANNUAL", date(2026, 9, 15))
after = register.as_of("MCA.AOC4.ANNUAL", date(2027, 6, 1))
print(f"AOC-4 as of 15-Sep-2026 -> v{before.version}")
print(f"AOC-4 as of  1-Jun-2027 -> v{after.version}")

print("\n2. CHANGE DETECTION")
print("=" * 70)
store = SnapshotStore(ROOT / "data" / "snapshots")
fixtures = ROOT / "tests" / "fixtures"
check_source(LocalFileSource("mca_circulars", fixtures / "mca_circulars_v1.txt"), store)
event = check_source(LocalFileSource("mca_circulars", fixtures / "mca_circulars_v2.txt"), store)
if event:
    candidates = find_affected_obligations(event, register.all_latest())
    print("possibly affected obligations:")
    for c in candidates:
        print(f"   - {c.obligation_id}: {c.match_reason}")

print("\n3. RETRIEVAL")
print("=" * 70)
raw = (ROOT / "data" / "corpus" / "companies_act_2013_extract.txt").read_text()
chunks = chunk_statute_text(raw, act="Companies Act, 2013",
                             source_url="https://www.indiacode.nic.in/handle/123456789/2114")
index = CorpusIndex(chunks)

for question in [
    "When is Form AOC-4 due after the AGM?",
    "What is the GST rate on restaurant services?",
]:
    print(f"\nQ: {question}")
    result = grounded_answer(index, question, min_score=0.3)
    if not result["grounded"]:
        print(f"   -> REFUSED: {result['message']}")
    else:
        top = result["answer_material"][0]
        print(f"   -> {top['citation']}")
print()