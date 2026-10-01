from lv_eval.metrics import aggregate
from lv_eval.models import EvaluationResult, ExpectedAnswer, ResourceUsage


def result(run_id: str):
    return EvaluationResult(run_id=run_id, case_id="c1", method="rule_only", mode="mock", status="completed",
                            confirmed_level=None, review_required=True, findings=[], source_scope=[], actually_read=[], usage=ResourceUsage())


def test_repeats_are_not_independent_cases():
    gold = {"c1": ExpectedAnswer(case_id="c1", project_id="p1", review_status="draft", confirmed_level=None, criteria={}, notes="")}
    row = aggregate([result("r1"), result("r2")], gold)[0]
    assert row["unique_cases"] == 1
    assert row["runs"] == 2
    assert row["final_lv_denominator"] == 1
    assert row["repeat_group_denominator"] == 1
    assert row["evidence_errors"] is None
