"""두 DB의 LLM 답을 기술 × 레포 × 조건마다 비교한다(오프라인, 비용 0). 일치도이지 정확도가 아니다(정확도는 gold.py의 정답 세트로 잰다).

예: 기준 DB(Opus 답, out/github.sqlite) ↔ 비교 DB(Haiku 답, out/model-compare/haiku.sqlite, 같은 수집 결과의 사본).
각 DB에서 기술 × 레포마다 지정한 모델이 낸 가장 최근 LLM 답(LLM 판정이나 그림자 실행)을 쓴다. 현재 판정으로 고르지 않는다:
비교 DB는 기준 DB의 사본이라, 비교 모델 호출이 실패·중단된 기술은 현재 판정이 기준 모델의 답으로 남아 있다(같은 답끼리 비교하게 된다).
최종 상태는 두 답 모두에 지금 규칙을 다시 적용해 비교한다(규칙 버전 차이를 없앤다). 입력 해시는 확인하지 않는다(해시 계산 방식이 바뀐 답도 비교).
두 답이 본 파일이 다르면(예: workflow 파일을 넣기 전·후) 그 차이도 섞이므로 쌍마다 따로 표시한다.
"""
import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

import assess as A
import engine as E
import extract
import rejudge
import rubric_source as R
import skills as S

HERE = Path(__file__).resolve().parent
ITEMS = ['personal_scope', *R.CONDITIONS]
LABEL = {'met': '충족', 'not_met': '미충족', 'unknown': '근거 부족', 'conflict': '충돌', None: '없음'}


def root(db, aid):
    """LLM을 실제로 부른 판정(재사용·규칙 재적용 행은 비용 0이라 원래 호출을 따라간다)."""
    while True:
        row = db.execute('SELECT id, reused_from, model, effort, cost_usd, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, created_at, '
                         'shown_files FROM assessment WHERE id = ?', (aid,)).fetchone()
        if not row[1]: return row
        aid = row[1]


def potential(final, risks):
    """실행 기록형 조건을 모두 충족으로 가정한 LV(판정 아님). 같은 commit 실행 기록이 없어 둘 다 미확인일 때, 기록이 생기면 모델 차이가 LV를 바꾸는지 본다."""
    return E.level_of({k: dict(v, status='met', note=None) if k in E.RUN_RECORD else v for k, v in final.items()}, risks)[0]


def answers(db_path, login, cache, index, model):
    """({(기술, 레포): 지금 규칙으로 다시 적용한 판정 + 원래 호출의 모델·비용·토큰}, [이 모델의 실패한 호출])"""
    run, repos = A.load(db_path, login)
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    out = {}
    rows = db.execute("SELECT id, tech, repo, sha, mode, shown_files FROM assessment WHERE run_id = ? AND status = 'ok' AND mode IN ('llm', 'shadow') "
                      'ORDER BY id', (run['id'],)).fetchall()
    for aid, tech, full, sha, mode, shown in rows:  # id 순서라 같은 기술 × 레포는 가장 최근 답이 남는다
        r = root(db, aid)
        if model not in (r[2] or '').split(','): continue
        repo = next(r for r in repos if r['full_name'] == full)
        ev = next(e for e in repo['evals'] if e['sha'] == sha)
        path = cache / full.replace('/', '__')
        found = S.detect(path, sha, [dict(path=p, lines=r) for p, r in ev['units'].items()], index)['skills']
        res = rejudge.rejudge_one(db, (aid, tech, shown, mode), repo, ev, found[tech], path, check_input=False) if tech in found else None
        if res is None: continue
        quote = lambda v: v['llm_status'] == 'met' and v['status'] != 'met' and E.base_note(v['note']) not in (*E.NO_RETRY, E.RULE_ONLY)
        out[(tech, full)] = dict(
            id=aid, call_id=r[0], model=r[2], effort=r[3], cost=r[4] or 0, tokens=dict(input=r[5], output=r[6], cache_read=r[7], cache_write=r[8]),
            at=r[9], shown=sorted(json.loads(r[10] or '[]')), level=res['level'], blocked=res['blocked'], potential=potential(res['final'], res['risks']),
            llm={k: v['llm_status'] for k, v in res['final'].items()}, final={k: v['status'] for k, v in res['final'].items()},
            risks={k: v['llm_status'] for k, v in res['risks'].items()},
            met=sum(res['final'][c]['status'] == 'met' for c in R.CONDITIONS),
            quote_lowered=sorted(k for k, v in res['final'].items() if quote(v)))
    failed = [dict(id=i, tech=t, repo=f, status=s, cost=c or 0, output=o) for i, t, f, s, c, o in db.execute(
        "SELECT id, tech, repo, status, cost_usd, output_tokens FROM assessment WHERE run_id = ? AND status != 'ok' AND model = ? ORDER BY id",
        (run['id'], model))]
    db.close()
    return out, failed


def compare(base, other):
    pairs = sorted(set(base) & set(other))
    rows, conf, kinds = [], Counter(), {}
    for key in pairs:
        a, b = base[key], other[key]
        llm_same = [k for k in ITEMS if a['llm'][k] == b['llm'][k]]
        final_same = [k for k in ITEMS if a['final'][k] == b['final'][k]]
        conf.update(f"{LABEL[a['llm'][k]]}→{LABEL[b['llm'][k]]}" for k in ITEMS if a['llm'][k] != b['llm'][k])
        for k in ITEMS:
            kind = E.KIND.get(k, '개인 기여')
            s = kinds.setdefault(kind, [0, 0])
            s[0] += a['llm'][k] == b['llm'][k]
            s[1] += 1
        rows.append(dict(tech=key[0], repo=key[1], ids=(a['id'], b['id']), llm_agree=len(llm_same), final_agree=len(final_same), items=len(ITEMS),
                         risk_agree=sum(a['risks'][k] == b['risks'][k] for k in a['risks']), same_files=a['shown'] == b['shown'],
                         files_only=dict(base=sorted(set(a['shown']) - set(b['shown'])), other=sorted(set(b['shown']) - set(a['shown']))),
                         level=(a['level'], b['level']), potential=(a['potential'], b['potential']), met=(a['met'], b['met']),
                         quote_lowered=(len(a['quote_lowered']), len(b['quote_lowered'])),
                         differ=[dict(id=k, base=LABEL[a['llm'][k]], other=LABEL[b['llm'][k]]) for k in ITEMS if a['llm'][k] != b['llm'][k]]))
    total = len(pairs) * len(ITEMS)
    pct = lambda n, d: f'{n}/{d} ({n / d:.0%})' if d else '0/0'
    return dict(
        pairs=len(pairs), only_base=sorted(set(base) - set(other)), only_other=sorted(set(other) - set(base)),
        llm_agree=pct(sum(r['llm_agree'] for r in rows), total), final_agree=pct(sum(r['final_agree'] for r in rows), total),
        risk_agree=pct(sum(r['risk_agree'] for r in rows), len(pairs) * len(E.RISKS)),
        level_same=pct(sum(r['level'][0] == r['level'][1] for r in rows), len(pairs)),
        potential_same=pct(sum(r['potential'][0] == r['potential'][1] for r in rows), len(pairs)),
        by_kind={k: pct(*v) for k, v in sorted(kinds.items())}, confusion=dict(conf.most_common()),
        cost=dict(base=round(sum(base[k]['cost'] for k in pairs), 4), other=round(sum(other[k]['cost'] for k in pairs), 4)),
        output_tokens=dict(base=sum(base[k]['tokens']['output'] or 0 for k in pairs), other=sum(other[k]['tokens']['output'] or 0 for k in pairs)),
        models=dict(base=sorted({base[k]['model'] for k in pairs}), other=sorted({other[k]['model'] for k in pairs})),
        rows=rows)


def main():
    p = argparse.ArgumentParser(description='두 DB의 LLM 답을 조건별로 비교(비용 0, 일치도이지 정확도 아님)')
    p.add_argument('url', help='https://github.com/<계정> 또는 계정 이름')
    p.add_argument('--base', type=Path, default=HERE / 'out' / 'github.sqlite')
    p.add_argument('--base-model', default='claude-opus-5-5')
    p.add_argument('--other', type=Path, required=True)
    p.add_argument('--other-model', default=E.MODEL)
    p.add_argument('--cache', type=Path, default=HERE / '.cache' / 'repos')
    a = p.parse_args()
    login = extract.parse_login(a.url)
    index, _ = S.load_dictionary()
    (base, base_failed), (other, other_failed) = (answers(a.base, login, a.cache, index, a.base_model),
                                                  answers(a.other, login, a.cache, index, a.other_model))
    res = compare(base, other)
    res['failed'] = dict(base=base_failed, other=other_failed)
    out = a.other.parent / f"compare-{extract.now()[:19].replace(':', '')}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"기준 {res['models']['base']} ↔ 비교 {res['models']['other']} · 기술 × 레포 {res['pairs']}쌍(한쪽에만 있음: {res['only_base']} / {res['only_other']})")
    for side, rows in res['failed'].items():
        for f in rows: print(f"  실패한 호출({side}): {f['tech']} · {f['repo']} — {f['status']}, 출력 {f['output']}토큰, ${f['cost']}")
    print(f"  본 파일이 다른 쌍: {[(r['tech'], r['files_only']) for r in res['rows'] if not r['same_files']]}")
    print(f"  LLM 판단 일치 {res['llm_agree']} · 지금 규칙 적용 후 일치 {res['final_agree']} · 위험 일치 {res['risk_agree']} · LV 같음 {res['level_same']} · 잠재 LV 같음 {res['potential_same']}(실행 기록형 충족 가정)")
    print(f"  유형별 LLM 판단 일치 {res['by_kind']}")
    print(f"  어긋남(기준→비교) {res['confusion']}")
    print(f"  호출 비용(추정) 기준 ${res['cost']['base']} · 비교 ${res['cost']['other']} · 출력 토큰 {res['output_tokens']}")
    for r in res['rows']:
        print(f"  {r['tech']:10s} {r['repo'].split('/')[1][:12]:12s} LLM 일치 {r['llm_agree']}/{r['items']} · 규칙 후 {r['final_agree']}/{r['items']} · "
              f"충족 수 {r['met'][0]}→{r['met'][1]} · 인용 문제로 내린 충족 {r['quote_lowered'][0]}→{r['quote_lowered'][1]} · LV {r['level'][0]}→{r['level'][1]} · 잠재 LV {r['potential'][0]}→{r['potential'][1]}")
    print(f'  자세한 결과: {out}')


if __name__ == '__main__': main()
