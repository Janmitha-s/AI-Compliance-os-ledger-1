"""
A `Source` is one thing you watch for changes: an eGazette listing page, an
MCA circulars page, a CBIC advisory feed, a specific notification PDF.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    url: str
    fetched_at: datetime
    content: str
    content_hash: str


class Source(Protocol):
    source_id: str

    def fetch(self) -> FetchResult: ...


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class LocalFileSource:
    """Reads a local file. Used in tests and for anything you're fed as a
    manual upload (e.g. a CS forwards you a circular PDF's extracted text)."""

    def __init__(self, source_id: str, path: Path):
        self.source_id = source_id
        self.path = Path(path)

    def fetch(self) -> FetchResult:
        content = self.path.read_text()
        return FetchResult(
            source_id=self.source_id,
            url=f"file://{self.path}",
            fetched_at=datetime.now(timezone.utc),
            content=content,
            content_hash=_hash(content),
        )


class HTTPSource:
    """Fetches a real URL. Requires the `requests` package and network
    access to the target domain. Run this from a machine with normal
    internet access — this is what you point at a real .gov.in page.
    """

    def __init__(self, source_id: str, url: str, timeout: int = 20):
        self.source_id = source_id
        self.url = url
        self.timeout = timeout

    def fetch(self) -> FetchResult:
        import requests
        resp = requests.get(self.url, timeout=self.timeout, headers={
            "User-Agent": "compliance-os-watcher/0.1 (contact: you@example.com)"
        })
        resp.raise_for_status()
        content = resp.text
        return FetchResult(
            source_id=self.source_id,
            url=self.url,
            fetched_at=datetime.now(timezone.utc),
            content=content,
            content_hash=_hash(content),
        )