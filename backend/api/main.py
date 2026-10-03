"""
Exposes the agent graph (graph/workflow.py) as an HTTP API.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from registry.store import RegisterStore
from corpus.chunker import chunk_statute_text
from corpus.index import CorpusIndex
from agents.audit import AuditLog
from graph.workflow import build_graph
from langgraph.types import Command

_DATA = Path(__file__).resolve().parent.parent / "data"
_register = RegisterStore(_DATA / "obligations").load_all()
_raw = (_DATA / "corpus" / "companies_act_2013_extract.txt").read_text()
_chunks = chunk_statute_text(_raw, act="Companies Act, 2013",
                              source_url="https://www.incometaxindia.gov.in")
_corpus = CorpusIndex(_chunks)
_audit = AuditLog()
_app_graph = build_graph(_register, _corpus, _audit)

app = FastAPI(title="compliance-os agent API", version="0.1.0")

# Without this, a browser fetch() from dashboard.html gets blocked before
# it even reaches these routes — the browser enforces same-origin by
# default and the server has to explicitly opt other origins in. "*" is
# fine for local development; lock this down to your real frontend's
# origin before this goes anywhere near production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AssessRequest(BaseModel):
    goal: str = Field(..., examples=["Assess compliance posture for SkyLogix"])
    profile: dict
    obligation_id: Optional[str] = None
    subject_id: Optional[str] = None
    as_of: Optional[date] = None


class DecisionRequest(BaseModel):
    approved: bool


class AssessResponse(BaseModel):
    thread_id: str
    status: str
    final_report: Optional[dict] = None
    pending_approval: Optional[dict] = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "obligations_loaded": len(_register.all_ids()),
        "obligations_unreviewed": len(_register.unreviewed()),
    }


@app.get("/obligations")
def list_obligations():
    return [
        {"obligation_id": ob.obligation_id, "title": ob.title, "act": ob.act,
         "section": ob.section, "confidence": ob.confidence, "subject": ob.subject}
        for ob in _register.all_latest()
    ]


@app.post("/assess", response_model=AssessResponse)
def start_assessment(req: AssessRequest):
    thread_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}}
    result = _app_graph.invoke({
        "goal": req.goal, "profile": req.profile,
        "obligation_id": req.obligation_id, "subject_id": req.subject_id,
        "as_of": req.as_of or date.today(),
    }, config=cfg)
    if "__interrupt__" in result:
        return AssessResponse(thread_id=thread_id, status="pending_approval",
                               pending_approval=result["__interrupt__"][0].value)
    return AssessResponse(thread_id=thread_id, status="completed", final_report=result["final_report"])


@app.post("/assess/{thread_id}/decision", response_model=AssessResponse)
def submit_decision(thread_id: str, req: DecisionRequest):
    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        result = _app_graph.invoke(Command(resume=req.approved), config=cfg)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"No pending run for thread_id={thread_id}: {e}")
    if "__interrupt__" in result:
        return AssessResponse(thread_id=thread_id, status="pending_approval",
                               pending_approval=result["__interrupt__"][0].value)
    return AssessResponse(thread_id=thread_id, status="completed", final_report=result["final_report"])