from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import EvaluationResult


def write_jsonl(path: Path, results: list[EvaluationResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(result.model_dump_json() + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_report(path: Path, rows: list[dict[str, Any]], results: list[EvaluationResult], mode: str) -> None:
    headers = ["method", "final_lv_accuracy", "criterion_accuracy", "coverage", "over_recognition", "under_recognition", "deferrals", "failure_rate", "avg_seconds", "total_model_calls", "total_tool_calls", "total_tokens", "total_cost_krw"]
    lines = [
        "# LV evaluation benchmark report",
        "",
        "> **synthetic / draft** — 사람이 의미와 예상 답안을 검토한 최종 평가가 아닙니다.",
        "",
        f"실행 모드: `{mode}`. 이 수치는 이 저장소의 RAG 합성 개발 사례와 현재 워크플로에만 적용됩니다.",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(row.get(key)) for key in headers) + " |")
    lines.extend([
        "",
        "## 해석 범위",
        "",
        "- 현재 자료는 연결·오류 경로 확인용 합성 개발 자료다. 사람 검토 정답이 없으므로 근거 오류는 N/A이며 우승 구성을 선언할 수 없다.",
        "- 호출·토큰·시간은 실제 사용량이다. mock/replay 토큰은 어댑터가 기록한 결정론적 추정치이며 실제 과금 토큰이 아니다. 가격표가 없으므로 비용은 N/A다.",
        "- Single/Multi-agent는 추가 모델 호출과 도구 호출을 사용한다. 차이는 구조 자체뿐 아니라 추가 자원 효과일 수 있다.",
        "- Rule-only는 명시 패턴에 강하지만 표현 변형과 의미 해석에 약하다. LLM-only는 직접 판정을 보존하므로 일관성·과대 인정 위험을 별도로 관찰해야 한다.",
        "- 고정 워크플로는 단계가 재현 가능하고, 에이전트는 필요한 자료를 선택할 수 있지만 탐색 예산과 누락 위험이 있다.",
        "",
        "## 사례 관찰",
        "",
    ])
    for method in sorted({item.method for item in results}):
        subset = [item for item in results if item.method == method]
        success = next((item for item in subset if item.status == "completed" and item.confirmed_level is not None), None)
        deferred = next((item for item in subset if item.status == "completed" and item.confirmed_level is None), None)
        failure = next((item for item in subset if item.status != "completed"), None)
        lines.append(f"- `{method}`: 인정 사례 `{success.case_id if success else '없음'}`, 보류 사례 `{deferred.case_id if deferred else '없음'}`, 시스템/예산 실패 사례 `{failure.case_id if failure else '없음'}`.")
    lines.extend([
        "",
        "## 다음 단계",
        "",
        "사람이 기준표와 실제 프로젝트 자료/기준 답안을 검토하고, 사전에 품질·범위·비용·시간 gate를 채운 뒤 30~50개 프로젝트 파일럿을 실행해야 한다. 서비스 연결 후에는 실제 업로드 파싱, 권한, 지연, 모델 변경, 프롬프트 인젝션, 관측/재시도 동작을 추가 검증한다.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_runner_report(path: Path, comparison: dict[str, Any]) -> None:
    lines = [
        "# Python vs LangGraph executor comparison",
        "",
        "> **replay / synthetic / draft** — 같은 저장 응답과 같은 분석 함수를 이 워크플로에서 비교한 결과입니다.",
        "",
        "| 항목 | 일반 Python | LangGraph StateGraph |",
        "| --- | --- | --- |",
    ]
    for metric in ("normal_result", "elapsed_seconds", "failure_preserved_stages", "restart_recovered", "restart_process_count", "model_calls_with_restart", "duplicate_model_calls", "duplicate_stage_results", "support_code_lines"):
        lines.append(f"| {metric} | {_fmt(comparison['python'].get(metric))} | {_fmt(comparison['langgraph'].get(metric))} |")
    lines.extend([
        "",
        "정상 결과 동일성은 최종 LV와 기준별 상태를 비교한다. 실패는 `interpret` 계산 뒤 체크포인트 저장 전 주입한다. 두 실행기 모두 로컬 SQLite를 사용하며 실패 프로세스 종료 후 별도 Python 프로세스에서 복구한다.",
        "",
        "체크포인트 전에 실패한 호출은 어느 실행기에서도 완료 상태로 저장할 수 없어 재호출된다. 시간은 단일 로컬 replay 관측치라 성능 우열의 근거가 아니다. 기능을 구현하지 않은 항목은 N/A로 표시해야 하며, 이 결과를 다른 그래프나 운영 구조로 일반화할 수 없다.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
