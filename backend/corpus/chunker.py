"""
Chunking rule: split by statutory structure (section boundaries), never by a
fixed character/token window — that can cut a proviso away from the section
it qualifies.

Each section in the source text starts with a line like:
    SECTION 137(1) Copy of financial statement to be filed with Registrar
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SECTION_HEADER = re.compile(r"^SECTION\s+(\S+)\s+(.*)$", re.IGNORECASE)

@dataclass
class Chunk:
    chunk_id: str
    act: str
    section: str
    heading: str
    text: str
    source_url: str


def chunk_statute_text(
    raw_text: str,
    act: str,
    source_url: str,
) -> list[Chunk]:
    lines = raw_text.splitlines()
    chunks: list[Chunk] = []
    current_section: str | None = None
    current_heading = ""
    buffer: list[str] = []

    def flush():
        if current_section is not None and buffer:
            text = "\n".join(buffer).strip()
            if text:
                chunks.append(Chunk(
                    chunk_id=f"{act}::{current_section}",
                    act=act,
                    section=current_section,
                    heading=current_heading,
                    text=text,
                    source_url=source_url,
                ))

    for line in lines:
        m = _SECTION_HEADER.match(line.strip())
        if m:
            flush()
            current_section, current_heading = m.group(1), m.group(2)
            buffer = []
        else:
            buffer.append(line)
    flush()
    return chunks