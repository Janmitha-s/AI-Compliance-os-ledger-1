"""
Report Generation Agent
--------------------------
Assembles the outputs of the earlier agents into a single structured
report object. In production this would be rendered to PDF/Word/Excel
using an LLM + templates; here it returns the structured dict that the
dashboard (frontend/dashboard.html) consumes directly.
"""
from datetime import date


def build_report(org: dict, gap_report: dict, okrs: list[dict]) -> dict:
    return {
        "generated_on": str(date.today()),
        "org_name": org["org_name"],
        "industry": org["industry"],
        "compliance_pct": gap_report["compliance_pct"],
        "high_risk_count": gap_report["high_risk_count"],
        "medium_risk_count": gap_report["medium_risk_count"],
        "gaps": gap_report["gaps"],
        "okrs": okrs,
    }
