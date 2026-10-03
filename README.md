# AI Compliance OS — Prototype

A minimal, runnable slice of the "Autonomous AI Compliance Operating System"
idea: multi-agent pipeline (document understanding → regulation matching →
gap analysis → OKR generation → report) plus an interactive dashboard where
a user enters a company's details — through a guided form or by pasting a
JSON profile in any shape — and gets back a live compliance ledger and OKRs.

Every agent here is rule-based so it runs with zero external services and
zero API keys. Each file is written so a specific piece (an LLM call, a
real crawler, a vector DB query) can be dropped in later without touching
the others — see "Where to plug in real AI" below.

## Structure3already
  have it (any object with `org_name`, `industry`, `employees`, `exports`,
  `documents[]`; extra fields are ignored).

Click **Load sample company** to see it prefilled, or **Run compliance
analysis** with your own data to get a live compliance ledger + OKRs.

**With the Python backend + API** (useful if you want the pipeline running
server-side, e.g. behind a real intake form or an upload-parsing step):
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
- `GET /report` — runs the pipeline on the bundled sample company (demo mode)
- `POST /analyze` — submit any company's details as JSON and get back the
  full report; this is the real entrypoint a production intake form would call

## Where to plug in real AI

| File | Swap this in |
|---|---|
| `document_agent.py` | OCR (e.g. Tesseract/AWS Textract) + an LLM extraction prompt over uploaded PDFs/images |
| `regulation_agent.py` | Scheduled crawlers/RSS/official APIs + embeddings into a vector DB (e.g. pgvector, Pinecone) |
| `compliance_agent.py` | Replace rule matching with RAG: embed org profile, retrieve nearest regulation chunks, confirm applicability with an LLM + citations |
| `okr_agent.py` | Let an LLM draft the objective wording and key results instead of the fixed templates, still grounded in the gap data |
| `report_agent.py` | Render to PDF/Word/Excel via an LLM + templates instead of returning JSON |

## Regulation sources

The regulation knowledge base (`backend/data/sample_regulations.json`,
mirrored in `frontend/dashboard.html`'s `REGULATIONS` array) mixes two kinds
of entries:

- **Industry-specific rules** (DGCA, FSSAI, CDSCO, environmental clearance,
  data protection) — illustrative, for demo purposes.
- **MCA / Registrar of Companies rules** — sourced from current guidance on
  Companies Act, 2013 obligations: AOC-4 (financial statements, 30 days from
  AGM), MGT-7/MGT-7A (annual return, 60 days from AGM), ADT-1 (auditor
  appointment, 15 days from AGM), DIR-3 KYC (director KYC — **now triennial**
  as of the Companies (Appointment and Qualification of Directors) Amendment
  Rules, 2025, effective 31 Mar 2026, replacing the old annual cycle), DPT-3
  (annual deposits return, due 30 June), and MSME-1 (half-yearly return of
  overdue MSME payments). These only match companies where `country` contains
  "India" (see `country_contains` in `compliance_agent.py` / `ruleMatches` in
  the dashboard).

**Known simplification:** these MCA filings are genuinely *recurring*
(annual or triennial), but the schema only tracks one `expiry` per document.
A filing marked with no expiry will show as permanently "OK" once entered,
even though AOC-4/MGT-7 must be refiled every year. A production version
should track a `next_due_date` per filing type (derived from the AGM date +
the statutory window) rather than reusing the document-expiry model built
for licenses/certificates.

## Build order

See the accompanying flowchart — build bottom-up (data → agents → pipeline
→ API → dashboard) so each layer can be tested before the next depends on it.
