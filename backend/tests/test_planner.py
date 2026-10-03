from agents.planner import build_plan


def test_default_assessment_goal_starts_with_full_calendar():
    plan = build_plan("Assess compliance posture for SkyLogix")
    assert plan.steps[0].kind == "full_calendar"


def test_filing_goal_gets_full_calendar_before_filing_prep():
    plan = build_plan("Prepare the AOC-4 filing for SkyLogix", obligation_id="MCA.AOC4.ANNUAL")
    kinds = [s.kind for s in plan.steps]
    assert kinds == ["full_calendar", "filing_prep"]


def test_filing_goal_without_an_obligation_id_falls_back_to_assessment():
    plan = build_plan("prepare the filing please")
    assert all(s.kind != "filing_prep" for s in plan.steps)


def test_filing_goal_passes_through_subject_id_for_the_tool_layer_to_check():
    plan = build_plan(
        "Prepare the DIR-3 KYC filing", obligation_id="MCA.DIR3KYC.ANNUAL", subject_id="00111111",
    )
    filing_step = next(s for s in plan.steps if s.kind == "filing_prep")
    assert filing_step.args["subject_id"] == "00111111"


def test_legal_question_only_uses_corpus_search():
    plan = build_plan("What does section 137 require?")
    assert [s.kind for s in plan.steps] == ["corpus_search"]


def test_plan_is_marked_rule_based():
    plan = build_plan("does POSH apply to us")
    assert plan.planner == "rule_based"