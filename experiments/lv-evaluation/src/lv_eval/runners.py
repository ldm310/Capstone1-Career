from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, TypedDict

from .corpus import ReadOnlyCaseTools, materialize_all
from .criteria import CriteriaTable, adjudicate
from .llm import LLMAdapter
from .methods import UsageTracker, interpret_evidence
from .models import Budget, CriterionFinding
from .rules import verify_findings


STAGES = ("prepare", "interpret", "verify", "decide")


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS python_checkpoints (thread_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
    return connection


def _load_python(path: Path, thread_id: str) -> dict[str, Any]:
    with _connect(path) as connection:
        row = connection.execute("SELECT state_json FROM python_checkpoints WHERE thread_id = ?", (thread_id,)).fetchone()
    return json.loads(row[0]) if row else {"completed_stages": [], "events": []}


def _save_python(path: Path, thread_id: str, state: dict[str, Any]) -> None:
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO python_checkpoints(thread_id, state_json) VALUES (?, ?) "
            "ON CONFLICT(thread_id) DO UPDATE SET state_json=excluded.state_json",
            (thread_id, json.dumps(state, ensure_ascii=False, sort_keys=True)),
        )


def run_python_workflow(*, case_id: str, tools: ReadOnlyCaseTools, table: CriteriaTable, budget: Budget,
                        adapter: LLMAdapter, checkpoint_path: Path, thread_id: str,
                        fail_after: str | None = None) -> dict[str, Any]:
    """Plain-Python executor with SQLite stage checkpoints and restart recovery."""
    started = time.perf_counter()
    tracker = UsageTracker(budget)
    state = _load_python(checkpoint_path, thread_id)
    for stage in STAGES:
        if stage in state["completed_stages"]:
            continue
        if stage == "prepare":
            state["materials"] = materialize_all(tools)
        elif stage == "interpret":
            findings = interpret_evidence(case_id, state["materials"], table, adapter, tracker)
            state["proposed"] = [item.model_dump(mode="json") for item in findings]
        elif stage == "verify":
            proposed = [CriterionFinding.model_validate(item) for item in state["proposed"]]
            checked = verify_findings(proposed, state["materials"], table)
            state["checked"] = [item.model_dump(mode="json") for item in checked]
        elif stage == "decide":
            checked = [CriterionFinding.model_validate(item) for item in state["checked"]]
            level, review = adjudicate(checked, table)
            state["confirmed_level"] = level
            state["review_required"] = review
        state["events"].append({"stage": stage, "event": "computed"})
        if fail_after == stage:
            raise RuntimeError(f"injected failure after {stage} before checkpoint")
        state["completed_stages"].append(stage)
        _save_python(checkpoint_path, thread_id, state)
    state["elapsed_seconds"] = time.perf_counter() - started
    state["model_calls_this_process"] = tracker.usage.model_calls
    state["executor"] = "python"
    return state


class GraphState(TypedDict, total=False):
    case_id: str
    materials: dict[str, str]
    proposed: list[dict[str, Any]]
    checked: list[dict[str, Any]]
    confirmed_level: str | None
    review_required: bool
    events: list[dict[str, str]]


def run_langgraph_workflow(*, case_id: str, tools: ReadOnlyCaseTools, table: CriteriaTable, budget: Budget,
                           adapter: LLMAdapter, checkpoint_path: Path, thread_id: str,
                           fail_after: str | None = None, resume: bool = False) -> dict[str, Any]:
    """The same four analysis functions wired through LangGraph StateGraph."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    tracker = UsageTracker(budget)

    def event(state: GraphState, stage: str) -> list[dict[str, str]]:
        return [*state.get("events", []), {"stage": stage, "event": "computed"}]

    def prepare(state: GraphState) -> dict[str, Any]:
        result = materialize_all(tools)
        if fail_after == "prepare":
            raise RuntimeError("injected failure after prepare before checkpoint")
        return {"materials": result, "events": event(state, "prepare")}

    def interpret(state: GraphState) -> dict[str, Any]:
        result = interpret_evidence(case_id, state["materials"], table, adapter, tracker)
        if fail_after == "interpret":
            raise RuntimeError("injected failure after interpret before checkpoint")
        return {"proposed": [item.model_dump(mode="json") for item in result], "events": event(state, "interpret")}

    def verify(state: GraphState) -> dict[str, Any]:
        proposed = [CriterionFinding.model_validate(item) for item in state["proposed"]]
        result = verify_findings(proposed, state["materials"], table)
        if fail_after == "verify":
            raise RuntimeError("injected failure after verify before checkpoint")
        return {"checked": [item.model_dump(mode="json") for item in result], "events": event(state, "verify")}

    def decide(state: GraphState) -> dict[str, Any]:
        checked = [CriterionFinding.model_validate(item) for item in state["checked"]]
        level, review = adjudicate(checked, table)
        if fail_after == "decide":
            raise RuntimeError("injected failure after decide before checkpoint")
        return {"confirmed_level": level, "review_required": review, "events": event(state, "decide")}

    graph = StateGraph(GraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("interpret", interpret)
    graph.add_node("verify", verify)
    graph.add_node("decide", decide)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "interpret")
    graph.add_edge("interpret", "verify")
    graph.add_edge("verify", "decide")
    graph.add_edge("decide", END)
    config = {"configurable": {"thread_id": thread_id}}
    started = time.perf_counter()
    with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
        compiled = graph.compile(checkpointer=saver)
        output = compiled.invoke(None if resume else {"case_id": case_id, "events": []}, config)
    output["elapsed_seconds"] = time.perf_counter() - started
    output["model_calls_this_process"] = tracker.usage.model_calls
    output["executor"] = "langgraph"
    return output
