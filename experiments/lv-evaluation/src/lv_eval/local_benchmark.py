"""Small public-source pilot; never reads draft gold from an older rubric."""
import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from .cli import ROOT, METHODS, _adapter, _plan
from .corpus import load_case, case_fingerprint
from .criteria import load_criteria
from .llm import LLMAdapter
from .models import ResourceUsage


class MeasuredAdapter(LLMAdapter):
    def __init__(self, inner):
        self.inner = inner
        self.model, self.provider = inner.model, inner.provider
        self.calls = 0
        self.input_tokens = self.output_tokens = 0

    def generate(self, **kwargs):
        self.calls += 1
        parsed, meta = self.inner.generate(**kwargs)
        self.input_tokens += meta.input_tokens
        self.output_tokens += meta.output_tokens
        return parsed, meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['mock', 'live'], required=True)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error('repeat must be positive')
    plan, budget = _plan()
    # Fail before starting a batch if credentials are absent. Never print their value.
    _adapter(args.mode, plan['model'], provider=plan['provider'])
    table_path = ROOT / 'config/rag.user-approved.criteria.json'
    table = load_criteria(table_path)
    case_path = ROOT / 'data/public-pilot/projects/ruizguille-rag-from-scratch/cases/source-review'
    records = []
    for repeat in range(args.repeat):
        for name, evaluate in METHODS.items():
            manifest, tools = load_case(case_path)
            adapter = MeasuredAdapter(_adapter(args.mode, plan['model'], provider=plan['provider'], temperature=plan['temperature']))
            started = time.perf_counter()
            try:
                params = (manifest.case_id, tools, table, budget, args.mode)
                result = evaluate(*params) if name == 'rule_only' else evaluate(*params, adapter)
                record = result.model_dump(mode='json')
                record['error'] = None
            except Exception as exc:
                record = dict(method=name, status='budget_exceeded' if 'budget exceeded' in str(exc) else 'system_error',
                              confirmed_level=None, findings=[], error=type(exc).__name__)
            record.update(repeat=repeat + 1, mode=args.mode, source_fingerprint=case_fingerprint(case_path, manifest),
                          criteria_fingerprint=hashlib.sha256(table_path.read_bytes()).hexdigest(),
                          actually_read=sorted(tools.read_paths), model_name=adapter.model if name != 'rule_only' else 'none')
            record['usage'] = ResourceUsage(
                model_calls=adapter.calls, tool_calls=len(tools.calls) if 'agent' in name else 0,
                input_tokens=adapter.input_tokens, output_tokens=adapter.output_tokens,
                elapsed_seconds=time.perf_counter()-started,
            ).model_dump()
            records.append(record)
            print(f'{repeat+1}/{args.repeat} {name}: {record["status"]}', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.jsonl').write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in records)+'\n')
    lines = [
        '# 사용자 확정 LV 기준 — 로컬 벤치마크', '',
        f'실행 모드: **{args.mode}**. 공개 프로젝트 1개 × 5개 구성 × {args.repeat}회 = {len(records)}회.',
        '자료: ruizguille/rag-from-scratch, commit `0f2f4927873fde7d8479c243a21a77ea8a391e9a`. 제출 코드는 실행하지 않았다.',
        'LV 정의는 사용자 확정. 세부 기준 ID와 자동 추출 규칙은 구현 초안이며 사람 검토 기준 답안은 없다.', '',
        '| LV | 핵심 기준 | 필요한 증거 |', '| --- | --- | --- |',
        '| LV1 | 기본 기능 구현·실행 | 구현 코드, 재현 가능한 실행 방법·결과 |',
        '| LV2 | 요구사항에 맞춘 연결·검증 | 연동 코드, 요구사항 대응 테스트, 적용 이유 |',
        '| LV3 | 문제 측정·분석·수정·효과와 한계 | 문제 분석, 변경 코드, 동일 조건 전후 평가, 결과 해석 |', '',
        '| 구성 | 완료/실행 | 평균 초(실패 포함) | 모델 호출 합계 | 도구 호출 합계 | 입력+출력 토큰 | LV 결과 |',
        '| --- | --- | --- | --- | --- | --- | --- |',
    ]
    for name in METHODS:
        items = [x for x in records if x['method'] == name]
        usage = [x['usage'] for x in items]
        levels = ', '.join(str(x['confirmed_level']) if x['confirmed_level'] else ('null' if x['status']=='completed' else '실행 실패') for x in items)
        lines.append(f'| {name} | {sum(x["status"]=="completed" for x in items)}/{len(items)} | '
                     f'{statistics.mean(x["elapsed_seconds"] for x in usage):.4f} | '
                     f'{sum(x["model_calls"] for x in usage)} | {sum(x["tool_calls"] for x in usage)} | '
                     f'{sum(x["input_tokens"]+x["output_tokens"] for x in usage)} | {levels} |')
    lines += ['', '## 해석', '',
        '- LV/기준별 정답 일치율·과대/과소 인정·근거 오류·비용: **N/A**. 이전 기준의 합성 답안을 재사용하지 않았다.',
        '- null은 자료 부족 또는 미지원 추출 기준으로 인한 보류이며 능력 0이 아니다. 실행 실패는 별도 집계했다.',
        '- 사례당 상한: 모델 24회, 도구 20회, 토큰 30,000, 시간 120초. Multi-agent는 합산한다. budget_exceeded는 이 한도를 초과한 실행이다.',
        '- 이 자료에는 실제 실행 로그와 전후 비교가 없다. 개인 기여는 별도 항목으로 보존하고 LV 필수 조건에서 제외했다.',
        '- 새 세부 기준 중 재현 방법·요구사항 테스트·적용 이유·변경 코드·한계 해석의 Rule-only 추출기는 미지원이며 unknown으로 처리한다.',
        '- 1개 프로젝트의 반복은 독립 표본 3개가 아니다. 이 결과로 우승 구성이나 LangGraph 도입 여부를 결정하지 않는다.',
        '- 토큰은 응답에서 확인된 사용량 합계다. 오류 응답에서 사용량이 없으면 해당 실패 요청의 토큰은 알 수 없다.',
    ]
    if args.mode == 'mock':
        lines += ['', '**실제 Gemini 벤치마크 미실행:** 실행 당시 `.env`의 GEMINI_API_KEY가 비어 있었다.',
                  '모델 호출 수는 모의 호출이며 토큰은 문자 수 기반 추정이다. 시간은 로컬 모의 실행 시간으로 실제 모델 지연을 나타내지 않는다.',
                  'mock은 규칙 추출기를 공유하므로 구성 간 의미 이해 품질 차이를 측정하지 못한다.']
    lines += ['', '## 재실행', '', '```zsh', 'cd /Users/idongmin/Desktop/capstone1-career/experiments/lv-evaluation',
              '.venv/bin/python -m lv_eval.local_benchmark --mode live --repeat 3 --output artifacts/runs/approved-lv-live', '```',
              '실험 폴더 `.env`에 GEMINI_API_KEY를 입력하고 저장한 뒤 실행한다. 실사용 응답은 Git 제외 경로에 저장한다.']
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
