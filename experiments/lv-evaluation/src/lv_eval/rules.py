from __future__ import annotations

import re

from .criteria import CriteriaTable
from .models import Citation, CriterionFinding, EvidenceKind, EvidenceStatus


PATTERNS: dict[str, list[tuple[EvidenceKind, re.Pattern[str]]]] = {
    "rag.use": [
        (EvidenceKind.CODE, re.compile(r"(?i)(similarity_search|vector_store\.search|retrieve\(|retriever\.invoke)")),
        (EvidenceKind.CODE, re.compile(r"(?i)((context|documents|chunks).{0,80}(prompt|answer|generate)|(prompt|answer|generate).{0,80}(context|documents|chunks))")),
    ],
    "rag.executed": [
        (EvidenceKind.RUN, re.compile(r"(?i)(RAG[_ -]?PATH|retrieval).{0,80}(PASS|SUCCESS|completed)")),
    ],
    "rag.contribution": [
        (EvidenceKind.CONTRIBUTION, re.compile(r"(?i)(I implemented|my contribution|implemented by applicant).{0,160}(retriev|RAG|vector)")),
    ],
    "rag.project_integration": [
        (EvidenceKind.CODE, re.compile(r"(?i)(route|endpoint|user flow|application output).{0,120}(retriev|RAG|answer)")),
    ],
    "rag.improvement": [
        (EvidenceKind.DOCUMENT, re.compile(r"(?i)(before|baseline).{0,80}\d+(?:\.\d+)?")),
        (EvidenceKind.DOCUMENT, re.compile(r"(?i)(after|improved).{0,80}\d+(?:\.\d+)?")),
        (EvidenceKind.DOCUMENT, re.compile(r"(?i)(problem|issue|failure).{0,120}(changed|fixed|improved|hybrid|rerank|chunk)")),
    ],
}

NEGATIVE_PATTERNS = {
    "rag.executed": re.compile(r"(?i)(RAG[_ -]?PATH|retrieval).{0,80}(FAIL|FAILED|not run)"),
    "rag.contribution": re.compile(r"(?i)(implemented by teammate|not my contribution)"),
    "rag.project_integration": re.compile(r"(?i)(not integrated|demo only)"),
}


def _citations(materials: dict[str, str], criterion_id: str) -> list[Citation]:
    found: list[Citation] = []
    for path, text in materials.items():
        for line_no, line in enumerate(text.splitlines(), 1):
            for kind, pattern in PATTERNS[criterion_id]:
                suffix = path.lower()
                eligible = (
                    (kind == EvidenceKind.CODE and suffix.endswith(".py"))
                    or (kind == EvidenceKind.RUN and suffix.endswith((".log", ".jsonl")))
                    or (kind == EvidenceKind.CONTRIBUTION and "contribution" in suffix)
                    or (kind == EvidenceKind.DOCUMENT and suffix.endswith(".md"))
                )
                if eligible and pattern.search(line):
                    found.append(Citation(
                        path=path,
                        line_start=line_no,
                        line_end=line_no,
                        quote=line.strip()[:300],
                        kind=kind,
                    ))
    return found


def extract_rule_findings(materials: dict[str, str], table: CriteriaTable) -> list[CriterionFinding]:
    findings: list[CriterionFinding] = []
    for definition in table.criteria:
        citations = _citations(materials, definition.id)
        required_pattern_count = len(PATTERNS[definition.id])
        matched_pattern_count = len({
            index
            for index, (kind, pattern) in enumerate(PATTERNS[definition.id])
            if any(
                pattern.search(text)
                and (
                    (kind == EvidenceKind.CODE and path.lower().endswith(".py"))
                    or (kind == EvidenceKind.RUN and path.lower().endswith((".log", ".jsonl")))
                    or (kind == EvidenceKind.CONTRIBUTION and "contribution" in path.lower())
                    or (kind == EvidenceKind.DOCUMENT and path.lower().endswith(".md"))
                )
                for path, text in materials.items()
            )
        })
        positive = matched_pattern_count == required_pattern_count
        negative_pattern = NEGATIVE_PATTERNS.get(definition.id, re.compile(r"a^"))
        negative = any(
            negative_pattern.search(text)
            and (
                (definition.id == "rag.executed" and path.lower().endswith((".log", ".jsonl")))
                or (definition.id == "rag.contribution" and "contribution" in path.lower())
                or (definition.id == "rag.project_integration" and path.lower().endswith(".py"))
            )
            for path, text in materials.items()
        )
        if positive and negative:
            status = EvidenceStatus.CONFLICT
            rationale = "허용 근거와 상반된 자료가 함께 발견됨"
        elif positive:
            status = EvidenceStatus.MET
            rationale = "필수 패턴을 허용된 자료 종류에서 모두 확인"
        elif negative:
            status = EvidenceStatus.NOT_MET
            rationale = "명시적인 미충족 자료를 확인"
        else:
            status = EvidenceStatus.UNKNOWN
            rationale = "충분한 의미 또는 근거를 규칙으로 확인할 수 없음"
        findings.append(CriterionFinding(
            criterion_id=definition.id,
            status=status,
            citations=citations,
            rationale=rationale,
            quote_present=bool(citations),
            evidence_sufficient=positive and not negative,
        ))
    return findings


def verify_findings(
    proposed: list[CriterionFinding], materials: dict[str, str], table: CriteriaTable
) -> list[CriterionFinding]:
    """Verify citation existence only; semantic states remain the interpreter's output."""
    valid_ids = {item.id for item in table.criteria}
    checked: list[CriterionFinding] = []
    for finding in proposed:
        if finding.criterion_id not in valid_ids:
            continue
        valid_citations: list[Citation] = []
        for citation in finding.citations:
            lines = materials.get(citation.path, "").splitlines()
            if 1 <= citation.line_start <= len(lines):
                actual = lines[citation.line_start - 1].strip()
                if citation.quote.strip() in actual or actual in citation.quote.strip():
                    valid_citations.append(citation)
        status = finding.status
        rationale = finding.rationale
        if status == EvidenceStatus.MET and not valid_citations:
            status = EvidenceStatus.UNKNOWN
            rationale = f"인용 위치를 원문에서 검증하지 못함: {rationale}"
        checked.append(finding.model_copy(update={
            "citations": valid_citations,
            "status": status,
            "quote_present": bool(valid_citations),
            "evidence_sufficient": status == EvidenceStatus.MET and bool(valid_citations),
            "rationale": rationale,
        }))
    present = {item.criterion_id for item in checked}
    for criterion_id in sorted(valid_ids - present):
        checked.append(CriterionFinding(
            criterion_id=criterion_id,
            status=EvidenceStatus.UNKNOWN,
            rationale="해석 결과에 기준이 누락됨",
        ))
    return sorted(checked, key=lambda item: item.criterion_id)
