"""
Compliance Matching Agent
--------------------------
In production this is a RAG step: embed the org profile, retrieve the
nearest regulation chunks from the vector DB, and let an LLM confirm
applicability with citations. Here the same *shape* of decision is made
with explicit rules, so the logic is transparent and easy to swap for a
real retriever later.
"""


def _rule_matches(org: dict, rule: dict) -> bool:
    if "industry_contains" in rule:
        needle = rule["industry_contains"]
        if needle != "*" and needle.lower() not in org["industry"].lower():
            return False
    if "employees_gte" in rule and org["employees"] < rule["employees_gte"]:
        return False
    if "exports" in rule and org.get("exports") is not rule["exports"]:
        return False
    if "country_contains" in rule:
        needle = rule["country_contains"]
        if needle.lower() not in (org.get("country") or "").lower():
            return False
    return True


def find_applicable_regulations(org: dict, regulations: list[dict]) -> list[dict]:
    applicable = []
    for reg in regulations:
        if _rule_matches(org, reg["applies_if"]):
            applicable.append(reg)
    return applicable
