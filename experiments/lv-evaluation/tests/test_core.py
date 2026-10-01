from pathlib import Path

import pytest

from lv_eval.cli import ROOT
from lv_eval.corpus import load_case
from lv_eval.criteria import adjudicate, load_criteria
from lv_eval.methods import evaluate_llm, evaluate_multi_agent, evaluate_rule, evaluate_single_agent, evaluate_workflow
from lv_eval.mock_adapter import MockAdapter
from lv_eval.models import Budget, EvidenceStatus


TABLE = load_criteria(ROOT / "config/rag.criteria.json")
BUDGET = Budget(max_model_calls_per_case=20, max_tool_calls_per_case=30, max_total_tokens_per_case=100000, max_elapsed_seconds_per_case=30)


def case(name: str):
    path = next((ROOT / "data/development/projects").glob(f"*/cases/{name}"))
    return load_case(path)


@pytest.mark.parametrize("name,level", [("mention_only", None), ("basic_lv1", "LV1"), ("project_lv2", "LV2"), ("improvement_lv3", "LV3"), ("test_without_run", None), ("conflicting_logs", None)])
def test_rule_levels(name, level):
    manifest, tools = case(name)
    result = evaluate_rule(manifest.case_id, tools, TABLE, BUDGET, "mock")
    assert result.confirmed_level == level


@pytest.mark.parametrize("evaluator", [evaluate_workflow, evaluate_single_agent, evaluate_multi_agent])
def test_llm_structures_use_shared_adjudication(evaluator):
    manifest, tools = case("project_lv2")
    result = evaluator(manifest.case_id, tools, TABLE, BUDGET, "mock", MockAdapter())
    assert result.confirmed_level == "LV2"
    if "agent" in result.method:
        assert result.usage.tool_calls >= 3
        assert set(result.actually_read) == set(manifest.files)


def test_llm_only_runs_and_preserves_direct_output():
    manifest, tools = case("basic_lv1")
    result = evaluate_llm(manifest.case_id, tools, TABLE, BUDGET, "mock", MockAdapter())
    assert result.confirmed_level == "LV1"


def test_case_tools_reject_path_escape():
    _, tools = case("basic_lv1")
    with pytest.raises(ValueError):
        tools.read_file("../../../../gold/expected.jsonl")


def test_conflict_requires_review():
    manifest, tools = case("conflicting_logs")
    result = evaluate_rule(manifest.case_id, tools, TABLE, BUDGET, "mock")
    statuses = {item.criterion_id: item.status for item in result.findings}
    assert statuses["rag.executed"] == EvidenceStatus.CONFLICT
    assert result.review_required is True
