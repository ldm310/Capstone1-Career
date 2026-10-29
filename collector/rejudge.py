"""규칙만 바뀌었을 때 다시 판정한다(오프라인, 비용 0).

현재 판정마다 저장된 LLM 답(llm_output_raw)에 지금 규칙을 다시 적용하고, 새 판정을 reused_from·지금 규칙 버전과 함께 쌓는다.
인용 검사는 그 판정 때 LLM에게 실제로 보여 준 파일(assessment.shown_files)로만 한다.
LLM에 보낼 입력이 그 답을 받을 때와 달라졌으면(예: 같은 commit 실행 기록이 생김) 옛 답을 쓰지 않고 「Claude 필요」로 알린다(assess.py로 판정).
규칙만으로 끝난 판정(rule_only)은 아직도 실행 기록이 없으면 그대로 다시 쌓고, 그 그림자 실행도 지금 규칙으로 다시 쌓는다.
"""
import argparse
import json
from pathlib import Path

import assess as A
import engine as E
import extract
import skills as S
import store

HERE = Path(__file__).resolve().parent


def rejudge_one(db, row, repo, ev, s, path, check_input=True):
    """row: (assessment id, 기술, 보여 준 파일 JSON, mode). 지금 규칙으로 다시 판정한 결과(저장 안 함).
    다시 판정할 수 없으면 None: 규칙만으로 끝났는데 실행 기록이 생겼거나, 입력이 달라졌거나, 저장된 LLM 답이 없을 때.
    입력 해시가 없는 옛 답(v1)은 입력이 같은지 알 수 없어 다시 적용하되 확인 사유를 남긴다(legacy_reuse).
    check_input=False는 비교 전용이다(compare_models): 입력이 달라도 저장된 답을 그 답이 본 파일로 다시 적용한다. 저장하면 안 된다."""
    aid, tech, shown_files, mode = row
    target, files, docs = A.materials(tech, repo, ev, s, path)
    fx, flags = A.facts(repo, ev, repo['own_commits'])
    now = E.input_hash(target, fx, files, docs)
    if mode == 'rule_only':
        if flags['ran']: return None
        final, risks = E.rule_only(flags)
        return dict(target=target, status='ok', mode='rule_only', usage=[], omitted=[], shown=[], retries=0,
                    final=final, risks=risks, level=None, blocked=0, input_hash=now, llm_output=None)
    old_hash, omitted = db.execute('SELECT input_hash, omitted_files FROM assessment WHERE id = ?', (aid,)).fetchone()
    if check_input and old_hash and old_hash != now: return None
    output = store.output_of(db, aid)
    if output is None: return None
    seen = set(json.loads(shown_files or '[]'))
    shown = {E.FACTS: fx, **{p: t for p, t, _ in [*files, *docs] if p in seen}}
    code = E.code_index([f for f in files if f[0] in seen])
    final, risks, level, blocked = E.apply(output, shown, code, flags)
    return dict(target=target, status='ok', mode='shadow' if mode == 'shadow' else 'llm', usage=[], omitted=json.loads(omitted or '[]'),
                shown=sorted(seen), retries=0, final=final, risks=risks, level=level, blocked=blocked, input_hash=old_hash, llm_output=output,
                legacy_reuse=old_hash is None)


def main():
    p = argparse.ArgumentParser(description='저장된 LLM 답에 지금 규칙을 다시 적용(비용 0)')
    p.add_argument('url', help='https://github.com/<계정> 또는 계정 이름')
    p.add_argument('--db', type=Path, default=HERE / 'out' / 'github.sqlite')
    p.add_argument('--cache', type=Path, default=extract.CACHE_DIR)
    p.add_argument('--min-own-lines', type=int, default=50)
    a = p.parse_args()
    login = extract.parse_login(a.url)
    store.require_consent(a.db, login)
    run, all_repos = A.load(a.db, login)
    index, _ = S.load_dictionary()
    ver = A.versions()
    db = store.connect(a.db)
    current = db.execute("SELECT id, tech, repo, sha, level, shown_files, mode FROM assessment WHERE run_id = ? AND is_current = 1 AND status = 'ok' "
                         'ORDER BY id', (run['id'],)).fetchall()
    shadows = {(t, r): row for row in db.execute("SELECT id, tech, repo, sha, level, shown_files, mode FROM assessment WHERE id IN (SELECT MAX(id) "
                                                 "FROM assessment WHERE run_id = ? AND mode = 'shadow' AND status = 'ok' GROUP BY tech, repo)",
                                                 (run['id'],)).fetchall() for t, r in [row[1:3]]}
    fmt = lambda lv: '미확인' if lv is None else f'LV{lv}'
    # 다시 판정한 행에는 그 LLM 답을 낸 모델·effort를 그대로 남긴다(지금 기본 모델이 아니라)
    made_by = lambda aid: db.execute('SELECT model, effort FROM assessment WHERE id = ?', (aid,)).fetchone()
    print(f"규칙 {ver['rule_version']}({ver['rule_hash'][:8]})로 다시 판정 · 추출 실행 {run['id']}")
    for aid, tech, full, sha, old_level, shown_files, mode in current:
        repo = next((r for r in all_repos if r['full_name'] == full), None)
        ev = next((e for e in (repo or {}).get('evals', []) if e['sha'] == sha), None)
        path = a.cache / full.replace('/', '__')
        found = S.detect(path, sha, [dict(path=p_, lines=r) for p_, r in ev['units'].items()], index)['skills'] if ev else {}
        if tech not in found: print(f'  건너뜀: {tech} · {full} — 지금 기술 찾기에서 이 기술이 나오지 않음'); continue
        ctx = (repo, ev, found[tech], path)
        out, src = rejudge_one(db, (aid, tech, shown_files, mode), *ctx), aid
        sh = shadows.get((tech, full)) if mode == 'rule_only' else None
        if out is None and sh and sh[3] == sha:  # 규칙만으로 끝났던 판정에 실행 기록이 생김: 입력이 같은 그림자 답이 있으면 현재 판정으로 쓴다
            out, src = rejudge_one(db, (sh[0], tech, sh[5], 'llm'), *ctx), sh[0]
        if out is None: print(f'  Claude 필요: {tech} · {full} — 입력이 바뀌었거나(예: 실행 기록이 생김) 저장된 LLM 답이 없음(assess.py로 판정)'); continue
        out['reused_from'] = src
        model, effort = made_by(src) if out['mode'] != 'rule_only' else (None, None)
        new = store.save_assessment(a.db, run['id'], out, extract.now(), model, effort, versions=ver, review=A.review_reasons(out))
        changed = [k for k, v in out['final'].items() if v['note'] and v['llm_status'] == 'met']
        print(f"■ {tech} · {full} {sha[:7]} [{out['mode']}]: {fmt(old_level)} → {fmt(out['level'])} (막힌 곳 {out['blocked']}) · "
              f"규칙이 내린 LLM 충족 {len(changed)}건" + (': ' + ', '.join(changed[:6]) if changed else ''))
        if out['mode'] == 'rule_only' and sh and sh[3] == sha:  # 그림자 실행은 규칙만으로 끝난 판정에만 다시 쌓는다(비교용)
            shadow = rejudge_one(db, (sh[0], tech, sh[5], 'shadow'), *ctx)
            if shadow:
                shadow['reused_from'] = sh[0]
                store.save_assessment(a.db, run['id'], shadow, extract.now(), *made_by(sh[0]), versions=ver, shadow_of=new,
                                      review=A.review_reasons(shadow))
    db.close()
    A.report_stat(a, run, all_repos, index, ver)


if __name__ == '__main__': main()
