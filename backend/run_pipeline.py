"""
Runs the full AI Compliance OS pipeline once, end to end, using the
sample data in data/. This mirrors the flowchart:

  Document Agent -> Regulation Agent -> Compliance Agent
  -> Gap Analysis Agent -> OKR Agent -> Report Agent

Usage:
    python run_pipeline.py
"""
import json
import os

from agents.document_agent import load_org_profile, normalize_org
from agents.regulation_agent import load_regulations
from agents.compliance_agent import find_applicable_regulations
from agents.gap_analysis_agent import analyze_gaps
from agents.okr_agent import generate_okrs
from agents.report_agent import build_report

BASE_DIR = os.path.dirname(__file__)


def run(org: dict | None = None, verbose: bool = True):
    """If org is None, runs on the bundled sample company (demo mode).
    If org is provided (e.g. submitted from the dashboard form, an
    upload-parsing step, or a POST body), it's normalized and run through
    the same pipeline — this is the path a real deployment uses."""
    if org is None:
        org = load_org_profile(os.path.join(BASE_DIR, "data", "sample_org.json"))
    else:
        org = normalize_org(org)

    regulations = load_regulations(os.path.join(BASE_DIR, "data", "sample_regulations.json"))

    applicable = find_applicable_regulations(org, regulations)
    gap_report = analyze_gaps(org, applicable)
    okrs = generate_okrs(gap_report)
    report = build_report(org, gap_report, okrs)

    if verbose:
        print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
