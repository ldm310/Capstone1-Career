from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .models import CriterionFinding, EvidenceStatus


class CriterionDefinition(BaseModel):
    id: str
    level: str
    mandatory_condition: str
    allowed_evidence: list[str]
    unverified_handling: str
    conflict_handling: str


class LevelDefinition(BaseModel):
    level: str
    includes: list[str]
    mandatory_criteria: list[str]
    description: str


class CriteriaTable(BaseModel):
    schema_version: str
    technology: str
    status: str
    reviewed_by_human: bool
    levels: list[LevelDefinition]
    criteria: list[CriterionDefinition]
    global_conflict_policy: str
    null_policy: str


def load_criteria(path: Path) -> CriteriaTable:
    return CriteriaTable.model_validate_json(path.read_text(encoding="utf-8"))


def adjudicate(
    findings: list[CriterionFinding], table: CriteriaTable
) -> tuple[str | None, bool]:
    """Shared level rule for rule-only, workflow, single-agent and multi-agent."""
    by_id = {finding.criterion_id: finding.status for finding in findings}
    confirmed: str | None = None
    review_required = False
    required_so_far: list[str] = []
    for level in table.levels:
        required_so_far.extend(level.mandatory_criteria)
        statuses = [by_id.get(item, EvidenceStatus.UNKNOWN) for item in required_so_far]
        if all(status == EvidenceStatus.MET for status in statuses):
            confirmed = level.level
        else:
            if any(status in {EvidenceStatus.UNKNOWN, EvidenceStatus.CONFLICT} for status in statuses):
                review_required = True
            break
    if any(value == EvidenceStatus.CONFLICT for value in by_id.values()):
        review_required = True
    return confirmed, review_required


def criteria_prompt(table: CriteriaTable) -> str:
    return json.dumps(table.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
