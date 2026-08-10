"""
OKR Intelligence Agent
------------------------
This is the differentiator from the brainstorm: instead of just listing
problems, every gap is converted into an Objective with measurable Key
Results, ranked by a priority score (legal impact + urgency).
"""

SEVERITY_WEIGHT = {"High": 40, "Medium": 20, "Low": 5}


def _priority_score(gap: dict) -> int:
    score = SEVERITY_WEIGHT[gap["severity"]]
    if "penalty" in gap.get("penalty_if_ignored", "").lower():
        score += 5
    if gap["status"] == "Missing":
        score += 15
    if gap["status"] == "Expired":
        score += 20
    if gap["status"].startswith("Expires in"):
        score += 10
    return min(score, 100)


def generate_okrs(gap_report: dict) -> list[dict]:
    okrs = []
    for gap in gap_report["gaps"]:
        if gap["severity"] == "Low":
            continue  # already compliant, no objective needed

        key_results = [
            f"Collect / renew: {gap['required_document']}",
            f"Verify against {gap['authority']} requirement ({gap['regulation_id']})",
            "Upload signed document to central repository",
            "Compliance officer sign-off",
        ]

        okrs.append({
            "objective": f"Resolve {gap['status'].lower()} status for {gap['required_document']}",
            "linked_regulation": gap["regulation_id"],
            "key_results": key_results,
            "progress_pct": 0,
            "priority_score": _priority_score(gap),
            "risk_if_ignored": gap["penalty_if_ignored"],
        })

    okrs.sort(key=lambda o: o["priority_score"], reverse=True)
    return okrs
