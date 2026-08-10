"""
FastAPI entrypoint for the AI Compliance OS demo.

Run with:
    pip install -r requirements.txt
    uvicorn main:app --reload

Then open http://localhost:8000/report to see the JSON, or open
../frontend/dashboard.html (update its API_URL constant) to see it
rendered as a dashboard.
"""
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from run_pipeline import run

app = FastAPI(title="AI Compliance OS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class OrgDocument(BaseModel):
    type: str
    issued: Optional[str] = None
    expiry: Optional[str] = None


class OrgProfile(BaseModel):
    org_name: str
    industry: str
    country: Optional[str] = "India"
    states: Optional[list[str]] = []
    employees: int = 0
    exports: bool = False
    documents: list[OrgDocument] = []


@app.get("/report")
def get_report():
    """Demo endpoint: runs the pipeline on the bundled sample company."""
    return run()


@app.post("/analyze")
def analyze_company(org: OrgProfile):
    """Real entrypoint: submit any company's details (from the dashboard
    intake form, an upload-parsing pipeline, or another system) and get
    back the full compliance report — gaps, risk score, and OKRs."""
    return run(org.model_dump())


@app.get("/health")
def health():
    return {"status": "ok"}
