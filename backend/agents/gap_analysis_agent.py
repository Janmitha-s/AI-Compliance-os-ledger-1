"""
Gap Analysis Agent + Risk Assessment Agent
--------------------------------------------
Compares required documents (from the compliance matching step) against
documents the org actually has on file, flags missing/expired items, and
produces a risk score per gap and an overall compliance percentage.
"""


def analyze_gaps(org: dict, applicable_regulations: list[dict]) -> dict:
    held = {d["type"]: d for d in org["documents"]}
    gaps = []

    for reg in applicable_regulations:
        required = reg["required_document"]
        doc = held.get(required)

        if doc is None:
            severity = "High"
            status = "Missing"
        elif doc["expired"]:
            severity = "High"
            status = "Expired"
        elif doc["expires_soon"]:
            severity = "Medium"
            status = f"Expires in {doc['days_to_expiry']} days"
        else:
            severity = "Low"
            status = "OK"

        gaps.append({
            "regulation_id": reg["id"],
            "authority": reg["authority"],
            "title": reg["title"],
            "required_document": required,
            "status": status,
            "severity": severity,
            "penalty_if_ignored": reg["penalty"],
        })

    total = len(gaps)
    ok_count = sum(1 for g in gaps if g["severity"] == "Low")
    compliance_pct = round((ok_count / total) * 100) if total else 100

    return {
        "gaps": gaps,
        "compliance_pct": compliance_pct,
        "high_risk_count": sum(1 for g in gaps if g["severity"] == "High"),
        "medium_risk_count": sum(1 for g in gaps if g["severity"] == "Medium"),
    }
