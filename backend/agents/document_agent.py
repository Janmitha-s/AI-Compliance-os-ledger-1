"""
Document Ingestion + Understanding Agent
-----------------------------------------
In production this agent would run OCR + an LLM extraction prompt over
uploaded PDFs/images/Word files. For this demo it loads structured JSON
that represents the *output* of that extraction step, so the rest of the
pipeline can be exercised end to end without external services.
"""
import json
from datetime import date, datetime


def normalize_org(org: dict) -> dict:
    """Takes a raw org profile (from a form, an uploaded JSON, or an API
    call) and fills in derived fields (expired / expires_soon / days_to_expiry)
    for every document. This is the one place document-shape assumptions
    live, so a real OCR+LLM extraction step can hand off here unchanged."""
    org.setdefault("documents", [])
    org.setdefault("exports", False)
    org.setdefault("employees", 0)

    today = date.today()
    for doc in org["documents"]:
        doc["expired"] = False
        doc["expires_soon"] = False
        if doc.get("expiry"):
            expiry = datetime.strptime(doc["expiry"], "%Y-%m-%d").date()
            doc["days_to_expiry"] = (expiry - today).days
            doc["expired"] = doc["days_to_expiry"] < 0
            doc["expires_soon"] = 0 <= doc["days_to_expiry"] <= 60
        else:
            doc["days_to_expiry"] = None

    return org


def load_org_profile(path: str) -> dict:
    """Loads a sample/demo org profile from disk and normalizes it."""
    with open(path, "r") as f:
        org = json.load(f)
    return normalize_org(org)
