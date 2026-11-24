#!/usr/bin/env python3
"""packet + 점검 에이전트 출력 -> to_stat.py가 읽는 점검 결과.
Usage: python3 apply_verdicts.py packets.json agent_output.json > verdicts.json
에이전트 출력에 없는 id, 형식이 틀린 verdict는 'unsure'로 둠(= 정황으로 내려감. 통과로 올리지 않음)."""
import json, sys

if __name__ == '__main__':
    pk = json.load(open(sys.argv[1], encoding='utf-8')); out = {x.get('id'): x for x in json.load(open(sys.argv[2], encoding='utf-8')) if isinstance(x, dict)}
    res = []
    for p in pk:
        v = out.get(p['id'], {}); verdict = v.get('verdict') if v.get('verdict') in ('pass', 'reject', 'unsure') else 'unsure'
        res.append(dict(repo=p['repo'], person=p['person'], key=p['judgment'], verdict=verdict, reason_code=v.get('reason_code'), reason=v.get('reason', '')))
    json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
