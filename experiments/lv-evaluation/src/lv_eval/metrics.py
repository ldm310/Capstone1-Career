from __future__ import annotations

from collections import defaultdict

from .models import EvaluationResult, ExpectedAnswer


LEVEL_RANK = {None: 0, "LV1": 1, "LV2": 2, "LV3": 3}


def aggregate(results: list[EvaluationResult], expected: dict[str, ExpectedAnswer]) -> list[dict[str, object]]:
    grouped: dict[str, list[EvaluationResult]] = defaultdict(list)
    for result in results:
        grouped[result.method].append(result)
    rows: list[dict[str, object]] = []
    for method, items in sorted(grouped.items()):
        completed = [item for item in items if item.status == "completed"]
        first_by_case: dict[str, EvaluationResult] = {}
        repeats: dict[str, list[EvaluationResult]] = defaultdict(list)
        for item in items:
            repeats[item.case_id].append(item)
            first_by_case.setdefault(item.case_id, item)
        comparable = [item for case_id, item in first_by_case.items() if case_id in expected and item.status == "completed"]
        final_matches = sum(item.confirmed_level == expected[item.case_id].confirmed_level for item in comparable)
        criterion_total = 0
        criterion_matches = 0
        over = under = deferrals = unnecessary_deferrals = 0
        for item in comparable:
            gold = expected[item.case_id]
            actual_rank = LEVEL_RANK[item.confirmed_level]
            gold_rank = LEVEL_RANK[gold.confirmed_level]
            over += actual_rank > gold_rank
            under += actual_rank < gold_rank
            deferrals += item.confirmed_level is None and item.review_required
            unnecessary_deferrals += item.confirmed_level is None and gold.confirmed_level is not None
            actual = {finding.criterion_id: finding.status for finding in item.findings}
            for criterion_id, wanted in gold.criteria.items():
                criterion_total += 1
                criterion_matches += actual.get(criterion_id) == wanted
        consistent_groups = [group for group in repeats.values() if len(group) > 1]
        consistent = sum(len({(x.status, x.confirmed_level, tuple((f.criterion_id, f.status) for f in x.findings)) for x in group}) == 1 for group in consistent_groups)
        usage = [item.usage for item in completed]
        human_reviewed = all(expected[item.case_id].review_status == "human_reviewed" for item in comparable) if comparable else False
        rows.append({
            "method": method,
            "unique_cases": len(first_by_case),
            "runs": len(items),
            "completed_runs": len(completed),
            "system_errors": sum(item.status == "system_error" for item in items),
            "budget_exceeded": sum(item.status == "budget_exceeded" for item in items),
            "failure_rate": (len(items) - len(completed)) / len(items) if items else None,
            "decided_cases": sum(item.confirmed_level is not None for item in comparable),
            "coverage": (sum(item.confirmed_level is not None for item in comparable) / len(comparable)) if comparable else None,
            "final_lv_matches": final_matches,
            "final_lv_denominator": len(comparable),
            "final_lv_accuracy": final_matches / len(comparable) if comparable else None,
            "criterion_matches": criterion_matches,
            "criterion_denominator": criterion_total,
            "criterion_accuracy": criterion_matches / criterion_total if criterion_total else None,
            "over_recognition": over,
            "under_recognition": under,
            "evidence_errors": None if not human_reviewed else 0,
            "evidence_error_denominator": None if not human_reviewed else criterion_total,
            "deferrals": deferrals,
            "unnecessary_deferrals": unnecessary_deferrals,
            "repeat_consistent_groups": consistent,
            "repeat_group_denominator": len(consistent_groups),
            "avg_seconds": sum(x.elapsed_seconds for x in usage) / len(usage) if usage else None,
            "total_model_calls": sum(x.model_calls for x in usage),
            "total_tool_calls": sum(x.tool_calls for x in usage),
            "total_tokens": sum(x.input_tokens + x.output_tokens for x in usage),
            "total_retries": sum(x.retries for x in usage),
            "total_cost_krw": None,
            "reference_status": "human_reviewed" if human_reviewed else "synthetic_draft",
        })
    return rows
