from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

from .criteria import CriteriaTable, adjudicate
from .llm import LLMAdapter
from .models import ModelResponse
from .rules import extract_rule_findings

T = TypeVar("T", bound=BaseModel)


def _materials_from_prompt(prompt: str) -> dict[str, str]:
    marker = "MATERIALS_JSON="
    if marker not in prompt:
        return {}
    raw = prompt.split(marker, 1)[1].split("\nEND_MATERIALS", 1)[0]
    return json.loads(raw)


def _criteria_from_prompt(prompt: str) -> CriteriaTable:
    marker = "CRITERIA_JSON="
    raw = prompt.split(marker, 1)[1].split("\nEND_CRITERIA", 1)[0]
    return CriteriaTable.model_validate_json(raw)


class MockAdapter(LLMAdapter):
    """Deterministic adapter that still emits real tool actions for agent loops."""

    provider = "mock"

    def __init__(self, model: str = "mock-rag-reader-v1") -> None:
        self.model = model

    def generate(self, *, operation: str, prompt: str, response_model: type[T]) -> tuple[T, ModelResponse]:
        if operation.endswith(".action"):
            payload = self._tool_action(prompt)
        else:
            materials = _materials_from_prompt(prompt)
            table = _criteria_from_prompt(prompt)
            findings = extract_rule_findings(materials, table)
            if "direct" in operation:
                level, review = adjudicate(findings, table)
                payload = {"findings": [item.model_dump(mode="json") for item in findings], "confirmed_level": level, "review_required": review}
            else:
                payload = {"findings": [item.model_dump(mode="json") for item in findings]}
        parsed = response_model.model_validate(payload)
        meta = ModelResponse(
            payload=parsed.model_dump(mode="json"),
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(parsed.model_dump_json()) // 4),
            raw_id=f"mock-{operation}",
        )
        return parsed, meta

    @staticmethod
    def _tool_action(prompt: str) -> dict[str, object]:
        state = json.loads(prompt.split("AGENT_STATE_JSON=", 1)[1])
        observations = state.get("observations", [])
        if not observations:
            return {"action": "list_files"}
        listed = next((item for item in observations if item["tool"] == "list_files"), None)
        if listed and not any(item["tool"] == "search_text" for item in observations):
            return {"action": "search_text", "query": "RAG|retriev|vector|context|contribution|before|after|PASS|FAIL"}
        files = listed["result"] if listed else []
        read = {item["argument"] for item in observations if item["tool"] == "read_file"}
        for path in files:
            if path not in read:
                return {"action": "read_file", "path": path}
        return {"action": "finish"}
