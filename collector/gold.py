"""정답 세트: 사람이 시스템 결과를 보기 전에 따로 적은 기대 LV·조건 판정을 넣고, 시스템 전체(규칙 + LLM)의 결과와 비교한다(비용 0).

순서: check_github.py(수집, 동의 필요) → gold.py template(빈 표) → 사람이 expected 칸을 채움 → gold.py import → assess.py(판정) → gold.py compare
정답은 판정 결과를 보기 전에 적고 넣는다. 판정보다 늦게 넣은 정답은 비교 결과에 따로 표시한다.
비교는 일치도이지 정확도 보증이 아니다. 정답 세트가 작으면(10~20건) 비율은 참고치다.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import assess as A
import engine as E
import extract
import rubric_source as R
import skills as S
import store

HERE = Path(__file__).resolve().parent
COLUMNS = ['login', 'repo', 'tech', 'sha', 'cond_id', 'condition', 'expected', 'case_tag', 'note']  # 조건 유형(시스템 규칙)은 보여 주지 않는다
LV_VALUES = ['미확인'] + [f'LV{n}' for n in range(6)]
COND_VALUES = {'충족': 'met', '미충족': 'not_met', '근거 부족': 'unknown', '충돌': 'conflict'}
COND_LABEL = {v: k for k, v in COND_VALUES.items()}
CONDS = ['personal_scope', *R.CONDITIONS]


def template(a, login):
    """판정 대상(기술 × 레포 × 평가 commit)마다 빈 정답 표를 만든다. 시스템 판정은 넣지 않는다(기술 찾기 결과만 씀)."""
    store.require_consent(a.db, login)
    run, repos = A.load(a.db, login)
    index, _ = S.load_dictionary()
    chosen, _ = A.targets(repos, a.cache, index, a.min_own_lines, None)
    out = a.out or Path(a.db).parent / 'gold' / f"{run['login']}.csv"
    if Path(out).exists() and not a.force: raise SystemExit(f'{out}가 이미 있습니다. 적어 둔 정답을 덮어쓰지 않으려면 다른 --out을 주거나 --force를 쓰세요')
    rows = []
    for tech, repo, ev, s, path, _ in chosen:
        base = dict(login=run['login'], repo=repo['full_name'], tech=tech, sha=ev['sha'], expected='', case_tag='', note='')
        rows.append(dict(base, cond_id='LV', condition='이 레포에서 이 기술의 LV (미확인 · LV0~LV5)'))
        rows.append(dict(base, cond_id='personal_scope', condition='본인이 작성한 코드인지 (개인 기여)'))
        rows += [dict(base, cond_id=c, condition=f"{v['condition']} — {v['evidence']}") for c, v in R.CONDITIONS.items()]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='', encoding='utf-8-sig') as fh:  # 엑셀에서 한글이 깨지지 않게 BOM을 붙인다
        w = csv.DictWriter(fh, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f'빈 정답 표: {out} · 기술 × 레포 {len(chosen)}개 · {len(rows)}줄')
    print('expected 칸 값 — LV 줄: ' + ' · '.join(LV_VALUES) + ' / 조건 줄: ' + ' · '.join(COND_VALUES) + ' (비우면 비교하지 않음)')
    print('판정 결과를 보기 전에 채우고 gold.py import로 넣으세요. 경계 사례는 case_tag에 적습니다(예: CI 없이 결과 파일만)')


def import_labels(a, path):
    with open(path, encoding='utf-8-sig') as fh: rows = list(csv.DictReader(fh))
    bad = [(i + 2, r.get('cond_id'), r.get('expected')) for i, r in enumerate(rows) if (r.get('expected') or '').strip() and not (
        (r['cond_id'] == 'LV' and r['expected'].strip() in LV_VALUES) or (r['cond_id'] in CONDS and r['expected'].strip() in COND_VALUES))]
    if bad: raise SystemExit('expected 값이 올바르지 않은 줄(줄 번호, cond_id, 값): ' + ', '.join(map(str, bad[:10])))
    filled = [r for r in rows if (r.get('expected') or '').strip()]
    if any(not (r.get('sha') or '').strip() for r in filled): raise SystemExit('sha 칸이 빈 줄이 있습니다(빈 표에 적힌 평가 commit을 그대로 두세요)')
    keys = Counter((r['login'].lower(), r['repo'], r['tech'], r['sha'].strip(), r['cond_id']) for r in filled)
    dup = [k for k, n in keys.items() if n > 1]
    if dup: raise SystemExit(f'같은 정답 칸이 두 번 이상 있습니다(어느 것이 맞는지 고른 뒤 다시 넣으세요): {dup[:5]}')
    for login in {r['login'] for r in filled}: store.require_consent(a.db, login)
    db = store.connect(a.db)
    stamp, saved, same = extract.now(), 0, 0
    with db:
        for r in filled:
            account = db.execute('SELECT id FROM account WHERE login = ?', (r['login'],)).fetchone()
            values = (r['expected'].strip(), (r.get('case_tag') or '').strip(), (r.get('note') or '').strip())
            old = db.execute('SELECT expected, case_tag, note FROM gold_label WHERE account_id = ? AND repo = ? AND tech = ? AND sha = ? AND cond_id = ? '
                             'AND labeler = ?', (account[0], r['repo'], r['tech'], r['sha'].strip(), r['cond_id'], a.labeler)).fetchone()
            if old == values: same += 1; continue  # 바뀌지 않은 정답은 처음 넣은 시각을 그대로 둔다(판정 전에 적었는지 보는 근거)
            db.execute('INSERT INTO gold_label (account_id, repo, tech, sha, cond_id, expected, case_tag, note, labeler, labeled_at) '
                       'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (account_id, repo, tech, sha, cond_id, labeler) DO UPDATE SET '
                       'expected = excluded.expected, case_tag = excluded.case_tag, note = excluded.note, labeled_at = excluded.labeled_at',
                       (account[0], r['repo'], r['tech'], r['sha'].strip(), r['cond_id'], *values, a.labeler, stamp))
            saved += 1
    db.close()
    print(f'정답 {saved}줄 저장 · 그대로인 정답 {same}줄 · 빈 줄 {len(rows) - len(filled)}개는 건너뜀 · 적은 사람 {a.labeler} · {stamp}')


def system_value(db, aid, cond_id):
    """비교할 시스템 값과 그 값을 정한 쪽. 규칙만으로 판정해 LLM이 보지 않은 조건은 '판정 안 함'(일치도에서 뺀다).
    정한 쪽: 미호출(LLM 안 부름) · 규칙(규칙 메모가 상태를 정함) · LLM(재검토 표시만 붙은 LLM 판단 포함)."""
    if cond_id == 'LV':
        level, mode = db.execute('SELECT level, mode FROM assessment WHERE id = ?', (aid,)).fetchone()
        return ('미확인' if level is None else f'LV{level}'), mode
    row = db.execute('SELECT final_status, llm_status, rule_note FROM finding WHERE assessment_id = ? AND cond_id = ?', (aid, cond_id)).fetchone()
    if not row: return None, None
    final, llm, note = row
    rule = E.base_note(note)
    if rule == E.RULE_ONLY: return '판정 안 함', '미호출'
    return COND_LABEL.get(final, final), ('규칙' if rule and rule != '근거 충돌' else 'LLM')


def compare(a, login):
    db = store.connect(a.db)
    store.require_consent(a.db, login)
    account = db.execute('SELECT id, login FROM account WHERE login = ?', (login,)).fetchone()
    run = db.execute('SELECT id FROM collect_run WHERE account_id = ? AND stopped IS NULL ORDER BY id DESC LIMIT 1', (account[0],)).fetchone()
    if not run: raise SystemExit(f'{login}의 끝까지 마친 수집이 없습니다')
    current = {(t, r): (aid, sha, at) for aid, t, r, sha, at in db.execute(
        "SELECT id, tech, repo, sha, created_at FROM assessment WHERE run_id = ? AND is_current = 1 AND status = 'ok'", (run[0],))}
    shadows = {sid: aid for aid, sid in db.execute("SELECT id, shadow_of FROM assessment WHERE run_id = ? AND mode = 'shadow' AND status = 'ok' "
                                                   'ORDER BY id', (run[0],))}  # 현재 판정 id → 가장 최근 그림자 id
    first = dict(db.execute("SELECT tech || '|' || repo, MIN(created_at) FROM assessment a JOIN collect_run r ON r.id = a.run_id "
                            "WHERE r.account_id = ? AND mode != 'shadow' GROUP BY tech, repo", (account[0],)).fetchall())
    labels = db.execute('SELECT repo, tech, sha, cond_id, expected, case_tag, labeler, labeled_at FROM gold_label WHERE account_id = ?',
                        (account[0],)).fetchall()
    rows, unmatched, late = [], [], []
    for repo, tech, sha, cond_id, expected, case_tag, labeler, labeled_at in labels:
        hit = current.get((tech, repo))
        if not hit: unmatched.append(dict(repo=repo, tech=tech, cond_id=cond_id, expected=expected)); continue
        aid, eval_sha, _ = hit
        got, by = system_value(db, aid, cond_id)
        shadow = None
        if aid in shadows and cond_id != 'LV':
            s = db.execute('SELECT final_status, llm_status FROM finding WHERE assessment_id = ? AND cond_id = ?', (shadows[aid], cond_id)).fetchone()
            shadow = s and dict(final=COND_LABEL.get(s[0], s[0]), llm=COND_LABEL.get(s[1], s[1]))
        if (first.get(f'{tech}|{repo}') or '9') < labeled_at: late.append(dict(repo=repo, tech=tech, cond_id=cond_id, labeled_at=labeled_at))
        kind = 'LV' if cond_id == 'LV' else E.KIND.get(cond_id, '개인 기여')
        rows.append(dict(repo=repo, tech=tech, cond_id=cond_id, kind=kind, expected=expected, system=got, by=by or '없음', match=expected == got,
                         case_tag=case_tag, labeler=labeler, sha_differs=sha != eval_sha, shadow=shadow))
    db.close()
    lv = [r for r in rows if r['cond_id'] == 'LV']
    skipped = [r for r in rows if r['by'] == '미호출']  # LLM을 부르지 않아 시스템이 판정하지 않은 조건(그림자 실행 값은 shadow에 따로 남긴다)
    cond = [r for r in rows if r['cond_id'] != 'LV' and r['by'] != '미호출']
    rate = lambda xs: f"{sum(r['match'] for r in xs)}/{len(xs)}" + (f" ({sum(r['match'] for r in xs) / len(xs):.0%})" if xs else '')
    # 그림자 신호: 그림자 실행에서 LLM은 충족이라 했는데 규칙이 막은 조건. 정답이 LLM 쪽이면 규칙이 너무 엄격하다는 근거다
    signals = [r for r in rows if r['shadow'] and r['shadow']['llm'] == '충족' and r['shadow']['final'] != '충족']
    shadow_rows = [r for r in rows if r['cond_id'] != 'LV' and r['shadow']]
    summary = dict(
        login=account[1], run_id=run[0], labels=len(labels), compared=len(rows),
        lv=dict(agree=rate(lv), confusion=Counter(f"{r['expected']}→{r['system']}" for r in lv if not r['match']),
                unknown_vs_lv0=sum({r['expected'], r['system']} == {'미확인', 'LV0'} for r in lv)),
        conditions=dict(agree=rate(cond), by_kind={k: rate([r for r in cond if r['kind'] == k]) for k in sorted({r['kind'] for r in cond})},
                        by_decider={k: rate([r for r in cond if r['by'] == k]) for k in sorted({r['by'] for r in cond})}),
        not_judged=len(skipped),
        shadow_agree=f"{sum(r['shadow']['final'] == r['expected'] for r in shadow_rows)}/{len(shadow_rows)}",
        shadow_signals=dict(llm_met_rule_blocked=len(signals), gold_sides_with_llm=sum(r['expected'] == '충족' for r in signals),
                            gold_sides_with_rule=sum(r['expected'] in ('근거 부족', '미충족') for r in signals)),
        boundary_cases={tag: rate([r for r in rows if r['case_tag'] == tag]) for tag in sorted({r['case_tag'] for r in rows if r['case_tag']})},
        late_labels=late, unmatched=unmatched, sha_differs=sum(r['sha_differs'] for r in rows),
        disagreements=[r for r in rows if not r['match']])
    out = Path(a.db).parent / 'gold' / f"compare-{account[1]}-{extract.now()[:19].replace(':', '')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"정답 비교 · {account[1]} · 정답 {len(labels)}줄 중 비교 {len(rows)}줄 (판정 없는 정답 {len(unmatched)}줄)")
    print(f"  기술 LV 일치 {summary['lv']['agree']} · 미확인↔LV0 혼동 {summary['lv']['unknown_vs_lv0']}건 · 어긋남 {dict(summary['lv']['confusion'])}")
    print(f"  조건 일치 {summary['conditions']['agree']}(LLM을 부르지 않아 판정 안 한 조건 {len(skipped)}개는 뺌) · 유형별 {summary['conditions']['by_kind']}")
    if shadow_rows: print(f"  그림자 실행 값으로 본 조건 일치 {summary['shadow_agree']}")
    print(f"  정한 쪽별 {summary['conditions']['by_decider']}")
    sg = summary['shadow_signals']
    print(f"  그림자 신호: LLM 충족·규칙이 막음 {sg['llm_met_rule_blocked']}건 → 정답이 LLM 쪽 {sg['gold_sides_with_llm']} · 규칙 쪽 {sg['gold_sides_with_rule']}")
    if summary['boundary_cases']: print(f"  경계 사례별 일치 {summary['boundary_cases']}")
    if late: print(f'  ! 판정 뒤에 넣은 정답 {len(late)}줄(결과를 보고 적었을 수 있음)')
    if summary['sha_differs']: print(f"  ! 정답을 매긴 commit과 평가 commit이 다른 줄 {summary['sha_differs']}개")
    print(f'  자세한 결과: {out}')
    return summary


def main():
    p = argparse.ArgumentParser(description='정답 세트: 빈 표 만들기 · 넣기 · 시스템 결과와 비교(비용 0)')
    p.add_argument('command', choices=['template', 'import', 'compare'])
    p.add_argument('target', help='template·compare: GitHub 계정 / import: 채운 CSV 경로')
    p.add_argument('--labeler', help='import: 정답을 적은 사람')
    p.add_argument('--out', type=Path, help='template: 저장 위치(기본 DB 옆 gold/<계정>.csv)')
    p.add_argument('--force', action='store_true', help='template: 같은 파일이 있어도 덮어씀')
    p.add_argument('--min-own-lines', type=int, default=50, help='assess.py와 같은 값')
    p.add_argument('--db', type=Path, default=HERE / 'out' / 'github.sqlite')
    p.add_argument('--cache', type=Path, default=HERE / '.cache' / 'repos')
    a = p.parse_args()
    if a.command == 'import':
        if not a.labeler: p.error('import에는 --labeler(정답을 적은 사람)가 필요합니다')
        return import_labels(a, a.target)
    login = extract.parse_login(a.target)
    (template if a.command == 'template' else compare)(a, login)


if __name__ == '__main__': main()
