from pathlib import Path

from lv_eval.cli import ROOT
from lv_eval.corpus import load_case
from lv_eval.criteria import load_criteria
from lv_eval.llm import ReplayAdapter
from lv_eval.models import Budget
from lv_eval.runners import run_langgraph_workflow, run_python_workflow


def test_executors_have_same_normal_result(tmp_path: Path):
    case_dir = next((ROOT / "data/development/projects").glob("*/cases/project_lv2"))
    table = load_criteria(ROOT / "config/rag.criteria.json")
    replay = ROOT / "data/replay/project_lv2.workflow.jsonl"
    budget = Budget(max_model_calls_per_case=4, max_tool_calls_per_case=10, max_total_tokens_per_case=10000, max_elapsed_seconds_per_case=10)
    _, py_tools = load_case(case_dir)
    py = run_python_workflow(case_id="project_lv2", tools=py_tools, table=table, budget=budget,
                             adapter=ReplayAdapter(replay, "saved"), checkpoint_path=tmp_path / "py.sqlite", thread_id="normal")
    _, lg_tools = load_case(case_dir)
    lg = run_langgraph_workflow(case_id="project_lv2", tools=lg_tools, table=table, budget=budget,
                               adapter=ReplayAdapter(replay, "saved"), checkpoint_path=tmp_path / "lg.sqlite", thread_id="normal")
    keys = ("confirmed_level", "review_required", "checked")
    assert {key: py[key] for key in keys} == {key: lg[key] for key in keys}
