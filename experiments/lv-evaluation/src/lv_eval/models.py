from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceStatus(str, Enum):
    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class EvidenceKind(str, Enum):
    CODE = "code"
    RUN = "run"
    CONTRIBUTION = "contribution"
    DOCUMENT = "document"


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    quote: str
    kind: EvidenceKind


class CriterionFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: str
    status: EvidenceStatus
    citations: list[Citation] = Field(default_factory=list)
    rationale: str
    quote_present: bool = False
    evidence_sufficient: bool = False


class ResourceUsage(BaseModel):
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0
    elapsed_seconds: float = 0.0
    cost_krw: float | None = None


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    case_id: str
    method: str
    mode: Literal["mock", "live", "replay"]
    status: Literal["completed", "system_error", "budget_exceeded"]
    confirmed_level: Literal["LV1", "LV2", "LV3"] | None
    review_required: bool
    findings: list[CriterionFinding]
    source_scope: list[str]
    actually_read: list[str]
    usage: ResourceUsage
    error: str | None = None
    dataset_labels: list[str] = Field(default_factory=lambda: ["synthetic", "draft"])
    source_fingerprint: str | None = None
    criteria_fingerprint: str | None = None
    model_name: str | None = None


class CaseManifest(BaseModel):
    case_id: str
    project_id: str
    technology: str
    split: Literal["development", "final"]
    labels: list[str]
    files: list[str]


class ExpectedAnswer(BaseModel):
    case_id: str
    project_id: str
    review_status: Literal["draft", "human_reviewed"]
    confirmed_level: Literal["LV1", "LV2", "LV3"] | None
    criteria: dict[str, EvidenceStatus]
    notes: str


class Budget(BaseModel):
    max_model_calls_per_case: int
    max_tool_calls_per_case: int
    max_total_tokens_per_case: int
    max_elapsed_seconds_per_case: float


class ModelResponse(BaseModel):
    payload: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    raw_id: str | None = None


class ToolAction(BaseModel):
    action: Literal["list_files", "read_file", "search_text", "finish"]
    path: str | None = None
    query: str | None = None
    findings: list[CriterionFinding] | None = None


def relative_files(root: Path, paths: list[Path]) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in paths)
