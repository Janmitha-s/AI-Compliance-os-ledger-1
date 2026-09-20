from pathlib import Path

from corpus.chunker import chunk_statute_text
from corpus.index import CorpusIndex, grounded_answer

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "data" / "corpus" / "companies_act_2013_extract.txt"
)


def load_index() -> CorpusIndex:
    raw = FIXTURE.read_text()
    chunks = chunk_statute_text(
        raw, act="Companies Act, 2013",
        source_url="https://www.indiacode.nic.in/handle/123456789/2114",
    )
    return CorpusIndex(chunks)


def test_chunking_produces_one_chunk_per_section():
    raw = FIXTURE.read_text()
    chunks = chunk_statute_text(raw, act="Companies Act, 2013", source_url="https://x")
    sections = {c.section for c in chunks}
    assert sections == {"137(1)", "137(3)", "403", "164(2)"}


def test_every_chunk_carries_a_citeable_source():
    index = load_index()
    for c in index.chunks:
        assert c.act and c.section and c.source_url


def test_search_finds_the_right_section_for_a_plain_question():
    index = load_index()
    hits = index.search("when must AOC-4 financial statements be filed after the AGM")
    assert hits, "expected at least one hit"
    assert hits[0].chunk.section == "137(1)"


def test_search_distinguishes_penalty_from_filing_deadline():
    index = load_index()
    hits = index.search("what happens if a company does not file on time penalty")
    top_sections = {h.chunk.section for h in hits[:2]}
    assert top_sections & {"137(3)", "403"}


def test_citation_string_contains_act_section_and_source():
    index = load_index()
    hit = index.search("director disqualification three years")[0]
    citation = hit.citation()
    assert "Companies Act, 2013" in citation
    assert "164(2)" in citation
    assert "indiacode.nic.in" in citation


def test_grounded_answer_refuses_when_nothing_relevant():
    index = load_index()
    result = grounded_answer(index, "what is the capital gains tax rate on listed equity", min_score=5.0)
    assert result["grounded"] is False
    assert result["answer_material"] == []


def test_grounded_answer_returns_citations_not_bare_text():
    index = load_index()
    result = grounded_answer(index, "AOC-4 due date after AGM", min_score=0.1)
    assert result["grounded"] is True
    for item in result["answer_material"]:
        assert "citation" in item and "Companies Act" in item["citation"]