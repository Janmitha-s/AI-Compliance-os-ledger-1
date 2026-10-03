"""
Retrieval layer. BM25 is the right starting point, not a placeholder for
embeddings: legal text is dense with exact tokens that matter verbatim —
section numbers, form codes, defined terms.

TWO REAL GAPS FOUND TESTING THIS AGAINST THE ACTUAL COMPANIES ACT TEXT,
both addressed below, neither fully solved:

1. FORM CODES AND ACRONYMS AREN'T IN THE ACT AT ALL. "AOC-4" is a form
   number defined in the Companies (Accounts) Rules 2014, not the Act
   itself. Routed around by resolving known form codes through the
   REGISTER first (see agents/retrieval_agent.py's FORM_CODE_TO_OBLIGATION),
   not by trying to teach BM25 free-text aliases — that was tried and
   diluted scores badly.

2. NO STEMMING MEANS MORPHOLOGICAL VARIANTS DON'T MATCH. "disqualifies"
   and "Disqualifications" (the literal heading of s.164) are different
   tokens to a naive tokenizer. Fixed with a Porter stemmer applied
   identically to corpus text at index time and queries at search time.
   Not a complete fix — "disqualifies" stems to "disqualifi" and
   "disqualification" stems to "disqualif", one character apart, a
   documented Porter-stemmer quirk on this exact -fy/-fication pair —
   routed around via a small query-side alias for this one pair.

min_score=1.5 in grounded_answer() below is empirically calibrated: a
genuine top match scores 3-7, a bare stemmer collision (e.g. "rating" vs
"rate") tops out around 1.2. If you add more sections and see a real
question refused or a wrong one answered, recheck this the same way:
print raw scores for both classes of query and see where the gap sits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from nltk.stem import PorterStemmer

from .chunker import Chunk

_stemmer = PorterStemmer()

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "on", "in", "to", "for", "and", "or", "as", "by", "with", "at",
    "this", "that", "it", "its", "what", "which", "who", "whom", "does",
    "do", "did", "has", "have", "had", "not", "no", "shall", "must", "may",
}

FORM_CODE_ALIASES: dict[str, str] = {
    "disqualifies": "disqualification disqualifications",
    "disqualify": "disqualification disqualifications",
}


def _expand_query(text: str) -> str:
    lowered = text.lower()
    additions = [expansion for term, expansion in FORM_CODE_ALIASES.items() if term in lowered]
    return text + " " + " ".join(additions)


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9()\-]+", text.lower())
    filtered = [t for t in tokens if t not in _STOPWORDS]
    return [_stemmer.stem(t) for t in filtered]


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
        scores = self._bm25.get_scores(_tokenize(_expand_query(query)))
        ranked = sorted(
            ((s, c) for s, c in zip(scores, self.chunks) if s > min_score),
            key=lambda pair: pair[0],
            reverse=True,
        )[:top_k]
        return [SearchHit(chunk=c, score=float(s)) for s, c in ranked]


def grounded_answer(index: CorpusIndex, question: str, top_k: int = 3, min_score: float = 1.5):
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