from __future__ import annotations

import json
import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from .corpus import ReadOnlyCaseTools, materialize_all, serialized_materials
from .criteria import CriteriaTable, adjudicate, criteria_prompt
from .llm import LLMAdapter
from .models import Budget, CriterionFinding, EvaluationResult, ResourceUsage, ToolAction
from .rules import extract_rule_findings, verify_findings


class FindingsOutput(BaseModel):
    findings: list[CriterionFinding]


class DirectOutput(FindingsOutput):
    confirmed_level: Literal["LV1", "LV2", "LV3"] | None
    review_required: bool


class UsageTracker:
    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self.usage = ResourceUsage()
        self.started = time.perf_counter()

    def model(self, meta: object) -> None:
        self.usage.model_calls += 1
        self.usage.input_tokens += getattr(meta, "input_tokens", 0)
        self.usage.output_tokens += getattr(meta, "output_tokens", 0)
        self.check()

    def tool(self) -> None:
        self.usage.tool_calls += 1
        self.check()

    def finish(self) -> ResourceUsage:
        self.usage.elapsed_seconds = time.perf_counter() - self.started
        return self.usage

    def check(self) -> None:
        if self.usage.model_calls > self.budget.max_model_calls_per_case:
            raise RuntimeError("model call budget exceeded")
        if self.usage.tool_calls > self.budget.max_tool_calls_per_case:
            raise RuntimeError("tool call budget exceeded")
        if self.usage.input_tokens + self.usage.output_tokens > self.budget.max_total_tokens_per_case:
            raise RuntimeError("token budget exceeded")
        if time.perf_counter() - self.started > self.budget.max_elapsed_seconds_per_case:
            raise RuntimeError("elapsed-time budget exceeded")


def _prompt(materials: dict[str, str], table: CriteriaTable, instruction: str) -> str:
    return (
        f"{instruction}\nCRITERIA_JSON={criteria_prompt(table)}\nEND_CRITERIA\n"
        f"MATERIALS_JSON={serialized_materials(materials)}\nEND_MATERIALS"
    )


def _result(case_id: str, method: str, mode: str, findings: list[CriterionFinding], table: CriteriaTable,
            scope: list[str], read: list[str], tracker: UsageTracker, direct: tuple[str | None, bool] | None = None) -> EvaluationResult:
    level, review = direct if direct is not None else adjudicate(findings, table)
    return EvaluationResult(
        run_id=str(uuid.uuid4()), case_id=case_id, method=method, mode=mode,
        status="completed", confirmed_level=level, review_required=review,
        findings=findings, source_scope=scope, actually_read=sorted(read), usage=tracker.finish(),
    )


def evaluate_rule(case_id: str, tools: ReadOnlyCaseTools, table: CriteriaTable, budget: Budget, mode: str) -> EvaluationResult:
    tracker = UsageTracker(budget)
    materials = materialize_all(tools)
    findings = extract_rule_findings(materials, table)
    return _result(case_id, "rule_only", mode, findings, table, sorted(tools.allowed_files), sorted(tools.read_paths), tracker)


def evaluate_llm(case_id: str, tools: ReadOnlyCaseTools, table: CriteriaTable, budget: Budget, mode: str, adapter: LLMAdapter) -> EvaluationResult:
    tracker = UsageTracker(budget)
    materials = materialize_all(tools)
    output, meta = adapter.generate(
        operation=f"{case_id}.llm_direct",
        prompt=_prompt(materials, table, "Judge every criterion and the final LV directly. A quote's existence is not automatically sufficient evidence."),
        response_model=DirectOutput,
    )
    tracker.model(meta)
    # Validate citations, but deliberately do not replace the model's final LV with shared rules.
    findings = verify_findings(output.findings, materials, table)
    return _result(case_id, "llm_only", mode, findings, table, sorted(tools.allowed_files), sorted(tools.read_paths), tracker,
                   direct=(output.confirmed_level, output.review_required))


def interpret_evidence(case_id: str, materials: dict[str, str], table: CriteriaTable,
                       adapter: LLMAdapter, tracker: UsageTracker) -> list[CriterionFinding]:
    output, meta = adapter.generate(
        operation=f"{case_id}.workflow_evidence",
        prompt=_prompt(materials, table, "Interpret evidence criterion by criterion. Do not assign a final LV."),
        response_model=FindingsOutput,
    )
    tracker.model(meta)
    return output.findings


def evaluate_workflow(case_id: str, tools: ReadOnlyCaseTools, table: CriteriaTable, budget: Budget,
                      mode: str, adapter: LLMAdapter) -> EvaluationResult:
    tracker = UsageTracker(budget)
    materials = materialize_all(tools)  # prepare
    proposed = interpret_evidence(case_id, materials, table, adapter, tracker)  # LLM interpret
    checked = verify_findings(proposed, materials, table)  # evidence check
    return _result(case_id, "fixed_workflow", mode, checked, table, sorted(tools.allowed_files), sorted(tools.read_paths), tracker)  # rules


def _agent_loop(case_id: str, role: str, tools: ReadOnlyCaseTools, table: CriteriaTable,
                budget: Budget, adapter: LLMAdapter, tracker: UsageTracker,
                seed_findings: list[CriterionFinding] | None = None) -> tuple[list[CriterionFinding], dict[str, str]]:
    observations: list[dict[str, object]] = []
    seen_materials: dict[str, str] = {}
    while True:
        state = {"role": role, "case_id": case_id, "observations": observations,
                 "seed_findings": [item.model_dump(mode="json") for item in (seed_findings or [])]}
        action, meta = adapter.generate(
            operation=f"{case_id}.{role}.action",
            prompt="Choose one read-only tool or finish. AGENT_STATE_JSON=" + json.dumps(state, ensure_ascii=False),
            response_model=ToolAction,
        )
        tracker.model(meta)
        if action.action == "finish":
            break
        if action.action == "list_files":
            result = tools.list_files()
            argument = "."
        elif action.action == "read_file" and action.path:
            result = tools.read_file(action.path)
            seen_materials[action.path] = result
            argument = action.path
        elif action.action == "search_text" and action.query:
            result = tools.search_text(action.query)
            for hit in result:
                path = str(hit["path"])
                seen_materials[path] = tools._resolve(path).read_text(encoding="utf-8")
            argument = action.query
        else:
            raise ValueError(f"invalid tool action: {action}")
        tracker.tool()
        observations.append({"tool": action.action, "argument": argument, "result": result})
    output, meta = adapter.generate(
        operation=f"{case_id}.{role}.findings",
        prompt=_prompt(
            seen_materials,
            table,
            "Return criterion findings from only the materials actually read. "
            + ("Review these analysis findings for omissions, misreadings, and conflicts: "
               + json.dumps([item.model_dump(mode="json") for item in seed_findings], ensure_ascii=False)
               if seed_findings else "Perform the primary evidence analysis."),
        ),
        response_model=FindingsOutput,
    )
    tracker.model(meta)
    return output.findings, seen_materials


def evaluate_single_agent(case_id: str, tools: ReadOnlyCaseTools, table: CriteriaTable, budget: Budget,
                          mode: str, adapter: LLMAdapter) -> EvaluationResult:
    tracker = UsageTracker(budget)
    proposed, seen = _agent_loop(case_id, "single_agent", tools, table, budget, adapter, tracker)
    checked = verify_findings(proposed, seen, table)
    return _result(case_id, "single_agent", mode, checked, table, sorted(tools.allowed_files), sorted(tools.read_paths), tracker)


def evaluate_multi_agent(case_id: str, tools: ReadOnlyCaseTools, table: CriteriaTable, budget: Budget,
                         mode: str, adapter: LLMAdapter) -> EvaluationResult:
    tracker = UsageTracker(budget)
    analysis, seen_analysis = _agent_loop(case_id, "analysis_agent", tools, table, budget, adapter, tracker)
    review, seen_review = _agent_loop(case_id, "review_agent", tools, table, budget, adapter, tracker, analysis)
    seen = {**seen_analysis, **seen_review}
    checked = verify_findings(review, seen, table)
    return _result(case_id, "multi_agent", mode, checked, table, sorted(tools.allowed_files), sorted(tools.read_paths), tracker)
