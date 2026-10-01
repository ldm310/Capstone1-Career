"""Run one pinned public-source case; never reads draft gold labels."""
import json
import time
from pathlib import Path

from .cli import ROOT, METHODS, _plan, _adapter
from .corpus import load_case, case_fingerprint
from .criteria import load_criteria
from .llm import LLMAdapter


class MeasuredAdapter(LLMAdapter):
    def __init__(self, inner):
        self.inner = inner
        self.model = inner.model
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def generate(self, **kwargs):
        self.calls += 1
        result, meta = self.inner.generate(**kwargs)
        self.input_tokens += meta.input_tokens
        self.output_tokens += meta.output_tokens
        return result, meta


def main():
    plan, budget = _plan()
    table = load_criteria(ROOT / "config/rag.confirmed-v2.json")
    case = ROOT / "data/public-pilot/projects/ruizguille-rag-from-scratch/cases/source-review"
    out = ROOT / "artifacts/runs/confirmed-v2-live"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for method, evaluator in METHODS.items():
        manifest, tools = load_case(case)
        adapter = None
        started = time.perf_counter()
        row = {"method": method, "mode": "live", "model": "none" if method == "rule_only" else plan["model"],
               "source_fingerprint": case_fingerprint(case, manifest)}
        try:
            args = (manifest.case_id, tools, table, budget, "live")
            if method != "rule_only":
                adapter = MeasuredAdapter(_adapter("live", plan["model"], temperature=plan["temperature"], provider=plan["provider"]))
                args += (adapter,)
            result = evaluator(*args)
            (out / f"{method}.json").write_text(result.model_dump_json(indent=2))
            row.update(status="completed", level=result.confirmed_level,
                       criteria={f.criterion_id: f.status.value for f in result.findings})
        except Exception as exc:
            # Provider error strings can contain request details; publish only error type/status.
            row.update(status="failed", level=None, error_type=type(exc).__name__,
                       http_status=getattr(exc, "code", None), criteria={})
        row.update(seconds=time.perf_counter()-started,
                   model_calls=adapter.calls if adapter else 0,
                   input_tokens=adapter.input_tokens if adapter else 0,
                   output_tokens=adapter.output_tokens if adapter else 0,
                   tool_calls=len(tools.calls), read_files=sorted(tools.read_paths))
        rows.append(row)
        (out / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        print(json.dumps(row, ensure_ascii=False), flush=True)
    lines = ["# 확정 LV 기준 — 첫 로컬 벤치마크", "",
             "사용자 확정 LV1~3을 v2 기준표로 반영. 세부 근거 해석은 검토 전이며, 상위 LV는 하위 LV 포함.",
             f"공개 RAG 프로젝트 1개, 구성별 1회. {plan['model']}, temperature=0. 제출 코드는 실행하지 않음.",
             "기존 합성 예상 답안은 사용하지 않음. 정확도·과대/과소 인정·근거 오류·비용·반복 일관성은 N/A.", "",
             "| 구성 | 실행 상태 | 확인 LV | 시간(s) | 모델 요청(실패 포함) | 도구 호출 | 입력 토큰 | 출력+추론 토큰 |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['method']} | {r['status']} | {r['level'] or 'null'} | {r['seconds']:.3f} | {r['model_calls']} | {r['tool_calls']} | {r['input_tokens']} | {r['output_tokens']} |")
    lines += ["", "실패 상세: " + "; ".join(f"{r['method']}: {r.get('error_type')} HTTP {r.get('http_status')}" for r in rows if r['status'] == 'failed'),
              "실패 결과의 null은 판정 보류가 아니라 결과 미생성이다. 토큰은 성공 응답에서 확인한 값만 합산하며, 실패 요청의 사용량은 미확인이다.",
              "A의 도구 호출에는 일괄 파일 로딩도 포함된다. 모형 호출이 없는 A의 시간과 실제 네트워크 호출을 포함한 B~E 시간을 구분해 해석한다.",
              "", "## 기준별 출력", "", "| 구성 | " + " | ".join(c.id for c in table.criteria) + " |",
              "|---|" + "---|" * len(table.criteria)]
    for r in rows:
        lines.append("| " + r['method'] + " | " + " | ".join(r['criteria'].get(c.id, 'N/A') for c in table.criteria) + " |")
    lines += ["", "현재 규칙 추출기는 신규 재현 방법·요구사항 테스트·적용 이유·엄격한 개선 기준을 충분히 해석하지 못해 unknown으로 처리한다. A는 확장 전 기준선이며 Rule-based 전체의 성능을 대표하지 않는다.",
              "공개 프로젝트에 실행 결과와 전후 평가가 부족하다. 개인 기여 확인과 사람 검토 정답은 별도 필요하다. 단일 사례·단일 실행으로 우승 기술을 정하지 않는다.",
              "", "실행: `.venv/bin/python -m lv_eval.pilot`", "원시 결과: `artifacts/runs/confirmed-v2-live/summary.json` (Git 제외)"]
    report = ROOT / "reports/confirmed-v2-live.md"
    report.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
