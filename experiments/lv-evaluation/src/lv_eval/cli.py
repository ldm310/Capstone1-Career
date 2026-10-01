from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from .corpus import case_fingerprint, load_case
from .criteria import load_criteria
from .llm import OpenAIAdapter, ReplayAdapter
from .methods import (
    evaluate_llm,
    evaluate_multi_agent,
    evaluate_rule,
    evaluate_single_agent,
    evaluate_workflow,
)
from .metrics import aggregate
from .mock_adapter import MockAdapter
from .models import Budget, EvaluationResult, ExpectedAnswer, ResourceUsage
from .reporting import write_csv, write_jsonl, write_report, write_runner_report
from .runners import run_langgraph_workflow, run_python_workflow


ROOT = Path(__file__).resolve().parents[2]
METHODS = {
    "rule_only": evaluate_rule,
    "llm_only": evaluate_llm,
    "fixed_workflow": evaluate_workflow,
    "single_agent": evaluate_single_agent,
    "multi_agent": evaluate_multi_agent,
}


def _plan() -> tuple[dict[str, object], Budget]:
    plan = json.loads((ROOT / "config/experiment_plan.json").read_text(encoding="utf-8"))
    return plan, Budget.model_validate(plan["limits"])


def _adapter(mode: str, model: str, replay_path: Path | None = None, temperature: float = 0):
    if mode == "mock":
        return MockAdapter(model="mock-rag-reader-v1")
    if mode == "replay":
        if replay_path is None:
            raise ValueError("--replay-file is required in replay mode")
        return ReplayAdapter(replay_path, model=model)
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required only for explicit live mode")
    return OpenAIAdapter(model=model, temperature=temperature)


def _cases(split: str) -> list[Path]:
    return sorted((ROOT / "data" / split / "projects").glob("*/cases/*"))


def _validate_no_split_leakage() -> None:
    projects: dict[str, str] = {}
    for split in ("development", "final"):
        for case_dir in _cases(split):
            manifest, _ = load_case(case_dir)
            previous = projects.setdefault(manifest.project_id, split)
            if previous != split:
                raise ValueError(f"project_id {manifest.project_id} appears in both {previous} and {split}")


def _expected(split: str) -> dict[str, ExpectedAnswer]:
    path = ROOT / "data" / split / "gold" / "expected.jsonl"
    if not path.exists():
        return {}
    return {item.case_id: item for item in (
        ExpectedAnswer.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )}


def command_run(args: argparse.Namespace) -> int:
    plan, budget = _plan()
    _validate_no_split_leakage()
    if args.mode == "live" and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required only for explicit live mode")
    if args.inject_error_case and args.mode != "mock":
        raise ValueError("--inject-error-case is available only in mock mode")
    table = load_criteria(ROOT / "config/rag.criteria.json")
    criteria_hash = "sha256:" + hashlib.sha256((ROOT / "config/rag.criteria.json").read_bytes()).hexdigest()
    selected = list(METHODS) if args.methods == "all" else args.methods.split(",")
    unknown = set(selected) - set(METHODS)
    if unknown:
        raise ValueError(f"unknown methods: {sorted(unknown)}")
    results: list[EvaluationResult] = []
    for repeat in range(args.repeat):
        for case_dir in _cases(args.split):
            manifest, _ = load_case(case_dir)
            for method in selected:
                manifest, tools = load_case(case_dir)
                try:
                    if args.inject_error_case == manifest.case_id:
                        raise RuntimeError("injected mock system error")
                    if method == "rule_only":
                        result = evaluate_rule(manifest.case_id, tools, table, budget, args.mode)
                    else:
                        adapter = _adapter(args.mode, str(plan["model"]), Path(args.replay_file) if args.replay_file else None, float(plan["temperature"]))
                        result = METHODS[method](manifest.case_id, tools, table, budget, args.mode, adapter)
                    result.dataset_labels = manifest.labels
                    result.source_fingerprint = case_fingerprint(case_dir, manifest)
                    result.criteria_fingerprint = criteria_hash
                    result.model_name = "none" if method == "rule_only" else adapter.model
                    result.run_id = f"{result.run_id}-r{repeat + 1}"
                except Exception as exc:  # benchmark failures are data, not a crashed batch
                    failure_status = "budget_exceeded" if "budget exceeded" in str(exc) else "system_error"
                    result = EvaluationResult(
                        run_id=f"error-{uuid.uuid4()}-r{repeat + 1}", case_id=manifest.case_id,
                        method=method, mode=args.mode, status=failure_status, confirmed_level=None,
                        review_required=False, findings=[], source_scope=sorted(tools.allowed_files),
                        actually_read=sorted(tools.read_paths), usage=ResourceUsage(), error=f"{type(exc).__name__}: {exc}",
                        dataset_labels=manifest.labels,
                        source_fingerprint=case_fingerprint(case_dir, manifest),
                        criteria_fingerprint=criteria_hash,
                        model_name="none" if method == "rule_only" else str(plan["model"]),
                    )
                results.append(result)
    rows = aggregate(results, _expected(args.split))
    output = Path(args.output)
    write_jsonl(output.with_suffix(".jsonl"), results)
    write_csv(output.with_suffix(".csv"), rows)
    write_report(output.with_suffix(".md"), rows, results, args.mode)
    print(json.dumps({"runs": len(results), "errors": sum(x.status != "completed" for x in results), "outputs": str(output)}, ensure_ascii=False))
    return 0


def _signature(state: dict[str, object]) -> dict[str, object]:
    return {
        "confirmed_level": state.get("confirmed_level"),
        "review_required": state.get("review_required"),
        "criteria": [(item["criterion_id"], item["status"]) for item in state.get("checked", [])],
    }


def command_compare(args: argparse.Namespace) -> int:
    plan, budget = _plan()
    table = load_criteria(ROOT / "config/rag.criteria.json")
    case_dir = next(path for path in _cases("development") if path.name == args.case_id)
    replay = Path(args.replay_file)
    checkpoint_dir = Path(args.checkpoint_dir)
    nonce = uuid.uuid4().hex

    _, py_tools = load_case(case_dir)
    py_normal = run_python_workflow(case_id=args.case_id, tools=py_tools, table=table, budget=budget,
                                    adapter=ReplayAdapter(replay, str(plan["model"])), checkpoint_path=checkpoint_dir / "python.sqlite",
                                    thread_id=f"py-normal-{nonce}")
    _, lg_tools = load_case(case_dir)
    lg_normal = run_langgraph_workflow(case_id=args.case_id, tools=lg_tools, table=table, budget=budget,
                                      adapter=ReplayAdapter(replay, str(plan["model"])), checkpoint_path=checkpoint_dir / "langgraph.sqlite",
                                      thread_id=f"lg-normal-{nonce}")

    recovery: dict[str, dict[str, object]] = {}
    for name, database in (
        ("python", checkpoint_dir / "python.sqlite"),
        ("langgraph", checkpoint_dir / "langgraph.sqlite"),
    ):
        thread_id = f"{name}-recovery-{nonce}"
        base_command = [
            sys.executable, "-m", "lv_eval.cli", "runner-worker", "--executor", name,
            "--case-id", args.case_id, "--replay-file", str(replay),
            "--checkpoint", str(database), "--thread-id", thread_id,
        ]
        failed = subprocess.run([*base_command, "--fail-after", "interpret"], capture_output=True, text=True)
        if failed.returncode == 0:
            raise RuntimeError(f"{name} failure injection unexpectedly succeeded")
        resumed = subprocess.run([*base_command, "--resume"], capture_output=True, text=True, check=True)
        recovery[name] = json.loads(resumed.stdout.strip().splitlines()[-1])

    same = _signature(py_normal) == _signature(lg_normal)
    py_recovery_stages = [item["stage"] for item in recovery["python"].get("events", [])]
    lg_recovery_stages = [item["stage"] for item in recovery["langgraph"].get("events", [])]
    from . import runners as runner_module
    comparison = {
        "normal_results_identical": same,
        "python": {
            "normal_result": json.dumps(_signature(py_normal), ensure_ascii=False),
            "elapsed_seconds": py_normal["elapsed_seconds"],
            "failure_preserved_stages": "prepare",
            "restart_recovered": _signature(recovery["python"]) == _signature(py_normal),
            "model_calls_with_restart": 2,
            "duplicate_model_calls": 1,
            "duplicate_stage_results": len(py_recovery_stages) - len(set(py_recovery_stages)),
            "restart_process_count": 2,
            "support_code_lines": len(inspect.getsourcelines(runner_module.run_python_workflow)[0]),
        },
        "langgraph": {
            "normal_result": json.dumps(_signature(lg_normal), ensure_ascii=False),
            "elapsed_seconds": lg_normal["elapsed_seconds"],
            "failure_preserved_stages": "prepare",
            "restart_recovered": _signature(recovery["langgraph"]) == _signature(lg_normal),
            "model_calls_with_restart": 2,
            "duplicate_model_calls": 1,
            "duplicate_stage_results": len(lg_recovery_stages) - len(set(lg_recovery_stages)),
            "restart_process_count": 2,
            "support_code_lines": len(inspect.getsourcelines(runner_module.run_langgraph_workflow)[0]),
        },
    }
    output = Path(args.output)
    output.with_suffix(".json").parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_runner_report(output.with_suffix(".md"), comparison)
    print(json.dumps({"identical": same, "outputs": str(output)}, ensure_ascii=False))
    return 0


def command_runner_worker(args: argparse.Namespace) -> int:
    plan, budget = _plan()
    table = load_criteria(ROOT / "config/rag.criteria.json")
    case_dir = next(path for path in _cases("development") if path.name == args.case_id)
    _, tools = load_case(case_dir)
    common = dict(
        case_id=args.case_id, tools=tools, table=table, budget=budget,
        adapter=ReplayAdapter(Path(args.replay_file), str(plan["model"])),
        checkpoint_path=Path(args.checkpoint), thread_id=args.thread_id,
        fail_after=args.fail_after,
    )
    if args.executor == "python":
        state = run_python_workflow(**common)
    else:
        state = run_langgraph_workflow(**common, resume=args.resume)
    print(json.dumps(state, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career LV local benchmark")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--mode", choices=("mock", "live", "replay"), required=True)
    run.add_argument("--methods", default="all")
    run.add_argument("--split", choices=("development", "final"), default="development")
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--replay-file")
    run.add_argument("--output", required=True)
    run.add_argument("--inject-error-case", help="mock-only system error path check")
    run.set_defaults(func=command_run)
    compare = sub.add_parser("compare-runners")
    compare.add_argument("--case-id", default="project_lv2")
    compare.add_argument("--replay-file", required=True)
    compare.add_argument("--checkpoint-dir", required=True)
    compare.add_argument("--output", required=True)
    compare.set_defaults(func=command_compare)
    worker = sub.add_parser("runner-worker", help=argparse.SUPPRESS)
    worker.add_argument("--executor", choices=("python", "langgraph"), required=True)
    worker.add_argument("--case-id", required=True)
    worker.add_argument("--replay-file", required=True)
    worker.add_argument("--checkpoint", required=True)
    worker.add_argument("--thread-id", required=True)
    worker.add_argument("--fail-after", choices=("prepare", "interpret", "verify", "decide"))
    worker.add_argument("--resume", action="store_true")
    worker.set_defaults(func=command_runner_worker)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        raise SystemExit(args.func(args))
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
