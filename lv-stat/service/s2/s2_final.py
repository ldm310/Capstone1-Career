#!/usr/bin/env python3
"""lv-stat 스테이징 마무리: 추출기 결과(vars-*.json)를 LLM 답 없이 카테고리 모듈의 finalize로 마무리한다.
2단계 S5 실행기(s2_s5.py)의 final 단계를 스테이징 서비스로 옮김(2026-11-27). LLM 보충은 끈다.

usage: python3 -I s2_final.py P01 [P02 ...]  → out/<pid>/final-<cat>.json (vars-<cat>.json마다)
- 모듈마다 finalize(person, data, {})를 부른다(답 없음). 흔적 있는 대상은 답이 없으니 모듈이 '대기'로 둔다.
  모듈이 그 변수 값을 비우면 계산에서 모름이 되고, 규칙 값을 남기면 그 값을 쓴다(모듈마다 다름).
- 흔적 없는 0(trace == 'no_trace') 대상은 LLM에 보내지 않으므로(사용자 결정 2026-11-26) 목록에서 뺀다.
  그래야 모듈이 대기로 두지 않고 0(안 씀)으로 남긴다.
- 모듈이 실패하면 규칙 값(vars) 그대로에 finalize_error를 붙여 쓰고 다음 카테고리로 간다.
- 결과마다 s5_policy(LLM 보충 끔, 뺀 no_trace 대상 수, 대기로 남은 대상 수)를 남긴다.
"""
import importlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2lib as L  # noqa: E402

MODULE_OF = {'prog': 'cat_prog_deploy', 'deploy': 'cat_prog_deploy', 'backend_a': 'cat_backend_a', 'backend_b': 'cat_backend_b',
             'de': 'cat_de', 'db': 'cat_db', 'fe': 'cat_fe', 'ai': 'cat_ai'}


def load_vars(pid):
    d = os.path.join(L.OUT, pid)
    res = {}
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = re.match(r'^vars-(\w+)\.json$', f)
        if m:
            with open(os.path.join(d, f), encoding='utf-8') as fh:
                res[m.group(1)] = json.load(fh)
    return res


def final(pid):
    """카테고리마다 final-<cat>.json을 쓴다. -> 마무리하지 못한(finalize_error) 카테고리 목록"""
    person = L.load_person(pid)
    failed = []
    for key, data in load_vars(pid).items():
        targets = data.get('s5_targets') or []
        keep = [t for t in targets if t.get('trace') != 'no_trace']
        data = dict(data, s5_targets=keep)
        policy = dict(llm='끔', no_trace_not_sent=len(targets) - len(keep), pending=len(keep))
        try:
            mod = importlib.import_module(MODULE_OF[key])
            # 사본을 넘긴다: 모듈이 고치다가 실패해도 data는 규칙 값 그대로 남는다
            fin = mod.finalize(person, json.loads(json.dumps(data)), {})
            fin['s5_policy'] = policy
            text = json.dumps(fin, ensure_ascii=False, indent=1)
        except Exception as e:      # 모듈 하나가 실패해도 나머지 카테고리는 마무리한다
            failed.append(key)
            text = json.dumps(dict(data, finalize_error=repr(e)[:300], s5_policy=policy), ensure_ascii=False, indent=1)
        with open(os.path.join(L.OUT, pid, f'final-{key}.json'), 'w', encoding='utf-8') as fh:
            fh.write(text)
    return failed


def main():
    for pid in sys.argv[1:]:
        failed = final(pid)
        print(pid, 'final', ('finalize_error: ' + ' '.join(failed)) if failed else 'ok', file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
