"""
Retrieval layer. BM25 over section-level chunks. A chunk never leaves this
module without its citation attached.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from .chunker import Chunk

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "on", "in", "to", "for", "and", "or", "as", "by", "with", "at",
    "this", "that", "it", "its", "what", "which", "who", "whom", "does",
    "do", "did", "has", "have", "had", "not", "no", "shall", "must", "may",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9()\-]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


@dataclass
class SearchHit:
    chunk: Chunk
    score: float

    def citation(self) -> str:
        return f"{self.chunk.act}, s.{self.chunk.section} ({self.chunk.source_url})"


class CorpusIndex:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("cannot build an index over zero chunks")
        self.chunks = chunks
        self._tokenized = [_tokenize(c.text + " " + c.heading) for c in chunks]
        self._bm25 = BM25Okapi(self._tokenized)

    def search(self, query: str, top_k: int = 3, min_score: float = 0.0) -> list[SearchHit]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            ((s, c) for s, c in zip(scores, self.chunks) if s > min_score),
            key=lambda pair: pair[0],
            reverse=True,
        )[:top_k]
        return [SearchHit(chunk=c, score=float(s)) for s, c in ranked]


def grounded_answer(index: CorpusIndex, question: str, top_k: int = 3, min_score: float = 0.5):
    hits = index.search(question, top_k=top_k, min_score=min_score)
    if not hits:
        return {
            "grounded": False,
            "answer_material": [],
            "message": "No sufficiently relevant provision found in the corpus "
                       "for this question. Route to a human reviewer rather "
                       "than guessing.",
        }
    return {
        "grounded": True,
        "answer_material": [
            {
                "section": h.chunk.section,
                "heading": h.chunk.heading,
                "text": h.chunk.text,
                "citation": h.citation(),
                "score": round(h.score, 3),
            }
            for h in hits
        ],
    }