"""
The register: every obligation JSON file on disk, loaded, validated for
provenance, and queryable by version-as-of-a-date.

Why this needs to be a real module and not "just read the JSON files":

1. PROVENANCE — an obligation with no source_url or section citation is not
   usable by a compliance product; a CS/CA cannot check it and an auditor
   cannot rely on it. This loader REFUSES to load an obligation missing that
   information, at import time, not at query time three months from now.

2. VERSIONING — law changes. When it does you do not edit the old JSON file
   in place (that destroys history and breaks any report generated last
   month). You add a new version with a new effective_from. RegisterStore
   resolves "what did the law say on date X" by picking the version whose
   [effective_from, effective_to) window contains X.

3. ONE OBLIGATION, MANY FILES — the on-disk layout is
       data/obligations/<obligation_id>/v<version>.json
   so `git log` on one file shows exactly how one rule evolved over time.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from domain.obligation import Obligation

REQUIRED_PROVENANCE_FIELDS = ("act", "section", "source_url", "effective_from")


class ProvenanceError(ValueError):
    """Raised when an obligation file is missing the fields that let a
    human verify it against the actual law."""


class RegisterStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._by_id: dict[str, list[Obligation]] = {}

    def load_all(self) -> "RegisterStore":
        self._by_id.clear()
        errors: list[str] = []

        for path in sorted(self.root.rglob("*.json")):
            raw = json.loads(path.read_text())
            missing = [f for f in REQUIRED_PROVENANCE_FIELDS if not raw.get(f)]
            if missing:
                errors.append(f"{path}: missing provenance field(s) {missing}")
                continue
            try:
                ob = Obligation(**raw)
            except Exception as e:
                errors.append(f"{path}: schema error: {e}")
                continue
            self._by_id.setdefault(ob.obligation_id, []).append(ob)

        for obligation_id, versions in self._by_id.items():
            versions.sort(key=lambda o: o.version)
            seen = set()
            for v in versions:
                if v.version in seen:
                    errors.append(f"{obligation_id}: duplicate version {v.version}")
                seen.add(v.version)

        if errors:
            raise ProvenanceError(
                f"{len(errors)} obligation file(s) rejected on load:\n  "
                + "\n  ".join(errors)
            )
        return self

    def all_ids(self) -> list[str]:
        return sorted(self._by_id.keys())

    def latest(self, obligation_id: str) -> Obligation:
        return self._by_id[obligation_id][-1]

    def as_of(self, obligation_id: str, on_date: date) -> Optional[Obligation]:
        """The version of this obligation that was in force on `on_date`."""
        candidates = [
            o for o in self._by_id.get(obligation_id, [])
            if o.effective_from <= on_date
            and (o.effective_to is None or on_date < o.effective_to)
        ]
        return candidates[-1] if candidates else None

    def history(self, obligation_id: str) -> list[Obligation]:
        return list(self._by_id.get(obligation_id, []))

    def unreviewed(self) -> list[Obligation]:
        """Everything still confidence=DRAFT — the CS/CA review queue."""
        return [
            v for versions in self._by_id.values() for v in versions
            if v.confidence == "DRAFT"
        ]

    def all_latest(self) -> list[Obligation]:
        return [versions[-1] for versions in self._by_id.values()]