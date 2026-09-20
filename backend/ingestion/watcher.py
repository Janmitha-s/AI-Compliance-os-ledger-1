"""
The watcher: fetch a Source, compare to what we saw last time, and if it
changed, emit a ChangeEvent for a human to look at.
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .source import FetchResult, Source


@dataclass
class ChangeEvent:
    source_id: str
    url: str
    detected_at: str
    previous_hash: Optional[str]
    new_hash: str
    diff_preview: str
    is_first_seen: bool


class SnapshotStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, source_id: str) -> Path:
        safe = source_id.replace("/", "_")
        return self.root / f"{safe}.json"

    def load(self, source_id: str) -> Optional[dict]:
        p = self._path(source_id)
        return json.loads(p.read_text()) if p.exists() else None

    def save(self, result: FetchResult) -> None:
        p = self._path(result.source_id)
        p.write_text(json.dumps({
            "source_id": result.source_id,
            "url": result.url,
            "fetched_at": result.fetched_at.isoformat(),
            "content_hash": result.content_hash,
            "content": result.content,
        }, indent=2))


def check_source(source: Source, store: SnapshotStore) -> Optional[ChangeEvent]:
    result = source.fetch()
    previous = store.load(source.source_id)

    if previous is None:
        store.save(result)
        return ChangeEvent(
            source_id=source.source_id,
            url=result.url,
            detected_at=result.fetched_at.isoformat(),
            previous_hash=None,
            new_hash=result.content_hash,
            diff_preview="(first time this source has been watched — full "
                         "content queued for review, not shown as a diff)",
            is_first_seen=True,
        )

    if previous["content_hash"] == result.content_hash:
        return None

    diff = "\n".join(difflib.unified_diff(
        previous["content"].splitlines(),
        result.content.splitlines(),
        lineterm="",
        n=2,
    ))
    store.save(result)
    return ChangeEvent(
        source_id=source.source_id,
        url=result.url,
        detected_at=result.fetched_at.isoformat(),
        previous_hash=previous["content_hash"],
        new_hash=result.content_hash,
        diff_preview=diff[:4000],
        is_first_seen=False,
    )


def run_watch_cycle(sources: list[Source], store: SnapshotStore) -> list[ChangeEvent]:
    events = []
    for s in sources:
        ev = check_source(s, store)
        if ev is not None:
            events.append(ev)
    return events