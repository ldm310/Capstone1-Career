"""흐름 3~7단계 실행 입구: DB의 최신 추출 결과 → 기술 찾기 → 기술별 판정(Claude API) → 내 STAT → DB 저장·출력.

규칙 먼저 판정: 같은 commit에 성공한 실행 기록이 없으면 Claude를 부르지 않고 규칙만으로 미확인으로 둔다(rule_only).
그림자 실행(--shadow-rate): 그런 경우 중 고정 표본은 Claude까지 돌려 비교만 한다(LV에 반영하지 않음).
같은 입력(input_hash)으로 받은 답이 있으면 다시 부르지 않고 지금 규칙만 다시 적용한다(--fresh면 다시 부름).
--dry-run은 Claude를 부르지 않고 평가 대상·판정 방식·예상 비용만 보여 준다.
실제 실행은 --budget-usd 안에서만 호출한다(호출 전마다 최악 비용을 계산해 넘으면 멈춘다).
"""
import argparse
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import engine as E
import extract
import skills as S
import store

HERE = Path(__file__).resolve().parent
DOC_EXT = ('.md', '.rst', '.txt')


def load(db_path, login):
    if not Path(db_path).exists(): raise SystemExit(f'{db_path}가 없습니다. 먼저 check_github.py를 실행하세요')
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    run = db.execute('SELECT * FROM collect_run WHERE lower(login) = lower(?) AND stopped IS NULL ORDER BY id DESC LIMIT 1', (login,)).fetchone()
    if not run: raise SystemExit(f'{login}의 끝까지 마친 추출 결과가 DB에 없습니다. 먼저 check_github.py를 실행하세요')
    repos = {r['id']: dict(r) for r in db.execute('SELECT * FROM repo WHERE run_id = ? AND error IS NULL', (run['id'],))}
    for r in repos.values():
        r['evals'] = [dict(e) for e in db.execute('SELECT * FROM eval_commit WHERE repo_id = ? AND own_lines > 0', (r['id'],))]
        r['own_commits'] = db.execute("SELECT COUNT(*), COALESCE(SUM(added), 0), COALESCE(MAX(added), 0) FROM own_commit "
                                      "WHERE repo_id = ? AND kind != 'name_only' AND is_merge = 0", (r['id'],)).fetchone()
        for e in r['evals']:
            e['units'] = {}
            for path, s, t in db.execute('SELECT path, line_start, line_end FROM evidence_line WHERE repo_id = ? AND sha = ?', (r['id'], e['sha'])):
                e['units'].setdefault(path, []).append([s, t])
    db.close()
    return dict(run), list(repos.values())


def run_lines(ev):
    """같은 commit에서 무엇을 돌렸는지(workflow·check run·status 이름과 결과). 무엇을 검사했는지는 workflow 파일과 함께 본다."""
    d = json.loads(ev.get('run_details') or 'null') or {}
    return ([f"  workflow 실행: {r['name']} ({r['path']}, {r['event']}) → {r['conclusion']}" for r in d.get('workflow_runs', [])]
            + [f"  check run: {c['name']} ({c['app']}) → {c['conclusion']}" for c in d.get('check_runs', [])]
            + [f"  commit status: {s['context']} → {s['state']}" for s in d.get('statuses', [])])


def run_flags(ev):
    """같은 commit에 성공한 실행(Actions 결과·check run 결론)이 있으면 ran. 실패만 있으면 run_failed. commit status는 세지 않는다(테스트가 아닐 수 있음)."""
    d = json.loads(ev.get('run_details') or 'null') or {}
    results = json.loads(ev['conclusions'] or '[]') + [c.get('conclusion') for c in d.get('check_runs', [])]
    ran = 'success' in results
    return ran, not ran and any(r in ('failure', 'timed_out', 'cancelled', 'action_required', 'startup_failure') for r in results)


def facts(repo, ev, own_commits):
    conclusions = json.loads(ev['conclusions'] or '[]')
    ran, failed = run_flags(ev)
    used = (repo['issues'] or 0) > 0  # 배포만으로는 활용이 아니다(기준표 LV3 「배포 URL만 존재」 불인정)
    relation = {1: 'develop이 main을 포함', 0: 'main·develop 갈라짐'}.get(repo['develop_contains_main'], '같은 commit이거나 develop 없음')
    text = '\n'.join([
        f"레포: {repo['full_name']} (기본 브랜치 {repo['default_branch']}, {relation})",
        f"평가 commit: {ev['sha']} ({ev['branches']})",
        f"이 commit에서 본인이 마지막으로 쓴 줄: {ev['own_lines']} / 전체 {ev['own_lines'] + ev['other_lines'] + ev['name_only_lines']}줄 (git blame, 생성 파일 제외)",
        f"본인 commit: {own_commits[0]}개 (계정 연결로 확인), 본인이 추가한 줄 {own_commits[1]}줄 (생성 파일 제외)"
        + (f", 가장 큰 commit 하나가 {own_commits[2]}줄({own_commits[2] / own_commits[1]:.0%}) — 한 번에 올린 코드는 직접 작성 여부를 git으로 알 수 없음"
           if own_commits[1] and own_commits[2] >= 100 and own_commits[2] / own_commits[1] >= 0.8 else ''),
        f"이 commit의 GitHub Actions 실행: {ev['actions']}건 (결과: {', '.join(map(str, conclusions)) or '없음'})",
        f"이 commit의 check run: {ev['check_runs']}건, commit status: {ev['statuses']}건",
        *run_lines(ev),
        f"같은 commit에 성공한 실행(Actions·check run): {'있음' if ran else '실패만 있음' if failed else '없음'}",
        f"레포 전체 GitHub Actions 실행: {repo['actions_all']}건",
        f"PR: {repo['pulls']}건 (병합 {repo['pulls_merged']}건, 본인이 연 것 {repo['pulls_own']}건)",
        f"이슈: {repo['issues']}건, 배포 기록(deployments): {repo['deployments']}건"])
    return text, dict(ran=ran, run_failed=failed, used=used)


def targets(repos, cache, index, min_own, only):
    """기술 × 레포마다 그 기술의 본인 줄이 가장 많은 평가 commit을 고른다(평가 commit은 미정이라 임시 규칙)."""
    best, missing = {}, []
    for repo in repos:
        path = Path(cache) / repo['full_name'].replace('/', '__')
        for ev in repo['evals']:
            if not (path / '.git').exists() or subprocess.run(['git', '-C', str(path), 'cat-file', '-e', f"{ev['sha']}^{{commit}}"],
                                                              capture_output=True).returncode:
                missing.append((repo['full_name'], ev['sha'])); continue  # clone이 없거나 그 commit이 없으면 빈 자료로 돈을 쓰지 않는다
            found = S.detect(path, ev['sha'], [dict(path=p, lines=r) for p, r in ev['units'].items()], index)
            for tech, s in found['skills'].items():
                key = (tech, repo['full_name'])
                if key not in best or s['own_lines'] > best[key][2]['own_lines']: best[key] = (repo, ev, s, path, found['unmatched'])
    chosen, skipped = [], []
    for (tech, full), (repo, ev, s, path, unmatched) in sorted(best.items(), key=lambda kv: -kv[1][2]['own_lines']):
        # 팀 사전에 없는 기술도 판정한다(사용자 결정). 공고와 비교할 때만 「사전에 없음」으로 표시한다.
        reason = f"본인 줄 {s['own_lines']} < {min_own}" if s['own_lines'] < min_own else None
        if only: reason = None if tech.lower() in only else '선택하지 않음'
        (skipped if reason else chosen).append((tech, repo, ev, s, path, reason))
    for full, sha in missing: print(f'  건너뜀: {full} {sha[:7]} — clone이나 commit이 캐시에 없음(check_github.py를 다시 실행하거나 --cache 확인)')
    return chosen, skipped


def materials(tech, repo, ev, s, path):
    order = sorted(s['files'].items(), key=lambda kv: -sum(e - b + 1 for b, e in kv[1]))
    texts = S.read_files(path, ev['sha'], [p for p, _ in order])
    files = [(p, '\n'.join(texts[p]), r) for p, r in order]
    docs = sorted(((p, r) for p, r in ev['units'].items() if p.lower().endswith(DOC_EXT)), key=lambda kv: -sum(e - b + 1 for b, e in kv[1]))
    if not any(p.lower() == 'readme.md' for p, _ in docs) and S.file_lines(path, ev['sha'], 'README.md'): docs.insert(0, ('README.md', []))
    tree = subprocess.run(['git', '-C', str(path), 'ls-tree', '-r', '--name-only', ev['sha'], '.github/workflows'],
                          capture_output=True, text=True).stdout.split()
    docs = [(p, ev['units'].get(p, [])) for p in tree if p.endswith(('.yml', '.yaml'))] + docs  # CI가 무엇을 돌리는지 보여 준다
    texts = S.read_files(path, ev['sha'], [p for p, _ in docs])
    docs = [(p, '\n'.join(texts[p]), r) for p, r in docs]
    target = dict(tech=tech, repo=repo['full_name'], sha=ev['sha'], branches=ev['branches'], signals=s['signals'], in_dictionary=s['in_dictionary'])
    return target, files, docs


def rule_hash(): return E.rule_hash(run_flags, facts, targets, report_stat)  # 기록 플래그·판정 대상·STAT 분모도 규칙이다


def versions():
    return dict(prompt_version=E.PROMPT_VERSION, rule_version=E.RULE_VERSION, rule_hash=rule_hash(), dict_version=S.dictionary_version())


def shadow_pick(target, rate):
    """그림자 실행 대상인지. 레포·commit·기술로 정하는 고정 표본이라 다시 돌려도 같은 대상이 뽑힌다."""
    if rate <= 0: return False
    h = int(hashlib.sha256(f"{target['repo']}|{target['sha']}|{target['tech']}".encode()).hexdigest()[:8], 16)
    return rate >= 1 or h / 0xFFFFFFFF < rate


def review_reasons(out):
    """사람이 확인할 사유(job.extraction_run.review_reasons와 같은 모양). 비면 확인할 것이 없다."""
    items = [{'항목': k, '사유': v['note']} for k, v in {**out.get('final', {}), **out.get('risks', {})}.items()
             if v.get('note') and (E.HOLD in v['note'] or E.OFFLINE in v['note'])]
    if out.get('legacy_reuse'):
        items.append({'항목': '입력', '사유': '입력 해시가 없는 옛 판정의 LLM 답을 다시 씀. 자료가 바뀌었을 수 있으니 --fresh로 다시 판정할 것'})
    if out.get('mode') == 'shadow':  # LLM은 근거가 있다는데 규칙이 막은 조건: 규칙이 너무 엄격한지 볼 신호
        items += [{'항목': k, '사유': f"그림자 실행: LLM은 충족, 규칙은 근거 부족({v['note']})"}
                  for k, v in out.get('final', {}).items() if v.get('llm_status') == 'met' and v['status'] != 'met']
    return items


class Claude:
    """Claude 클라이언트는 실제로 부를 일이 생길 때 만든다(규칙만으로 끝나거나 저장된 답을 쓰면 API 키가 없어도 된다)."""
    def __init__(self, usd): self.budget, self._cl = E.Budget(usd), None

    def client(self):
        if self._cl is None: self._cl = E.api_client()
        return self._cl


def plan(db, account_id, target, fx, flags, files, docs, ih, opts, shadow=False, readonly=False):
    """판정 방식: no_material(보여 줄 코드 없음) · rule_only(부르지 않음) · cache(저장된 답) · call(Claude 호출). engine.assess와 같은 순서로 본다.
    저장된 답은 같은 계정의 판정에서만 찾는다. 입력 해시가 없는 옛 답은 --reuse-legacy일 때만 쓴다."""
    shown = E.bundle(target, fx, files, docs)[1]
    if not any(p in shown for p in E.code_index(files)): return 'no_material', None
    if not flags['ran'] and not shadow: return 'rule_only', None
    found = None if opts.fresh else store.find_cached(db, ih, target, E.MODEL, E.EFFORT, account_id, legacy=opts.reuse_legacy, readonly=readonly)
    return ('cache' if found else 'call'), found


def judge_one(claude, db, account_id, ctx, target, fx, flags, files, docs, ih, opts, shadow=False):
    """판정 1건. Claude가 필요하면(실행 기록이 있거나 그림자 실행) 같은 입력의 저장된 답을 먼저 찾고, 없을 때만 부른다.
    입력 해시가 없는 옛 답은 그 답이 본 파일로만 다시 검사한다(지금 자료로 검사하지 않고, 입력 해시도 비워 둔다)."""
    how, found = plan(db, account_id, target, fx, flags, files, docs, ih, opts, shadow)
    if how == 'cache' and found['legacy']:
        import rejudge  # rejudge가 assess를 불러오므로 여기서 불러온다
        conn = store.connect(db)
        out = rejudge.rejudge_one(conn, (found['id'], target['tech'], found['shown'], 'shadow' if shadow else 'llm'), *ctx)
        conn.close()
        return dict(out, reused_from=found['id'], legacy_reuse=True)
    out = E.assess(claude.client() if how == 'call' else None, claude.budget, target, fx, flags, files, docs,
                   shadow=shadow, cached=found['output'] if found else None)
    if found: out.update(reused_from=found['id'])
    return out


def report(out):
    t = out['target']
    head = f"\n■ {t['tech']}{'' if t.get('in_dictionary', True) else '(사전 없음 → 공고 비교 불가)'} · {t['repo']} {t['branches']} {t['sha'][:7]}"
    if out.get('mode') == 'shadow': head = f"  └ 그림자 실행(비교용, LV 반영 안 함) {t['tech']}"
    cost = sum(u.get('cost_usd') or 0 for u in out['usage'])
    if out['status'] == 'no_material':
        print(f"{head} → 판정 안 함: 보여 줄 코드가 없음(파일 없음 또는 전부 길이 제한으로 빠짐) · 비용 $0"); return
    if out['status'] != 'ok':
        print(f"{head} → 판정 못 함({out['status']}) {json.dumps(out['usage'][-1] if out['usage'] else {}, ensure_ascii=False)}"); return
    if out['mode'] == 'rule_only':
        print(f"{head} → 미확인 (규칙만으로 판정: L0-03 {out['final']['L0-03']['note']} → Claude 안 부름) · 비용 $0"); return
    lv = '미확인' if out['level'] is None else f"LV{out['level']}"
    blocked = out['blocked']
    where = {None: '막힘 없음', 'personal_scope': '개인 기여 미확인', 'risk': '위험 적용 여부 미확인으로 LV2 이상 보류'}.get(blocked, f'LV{blocked}에서 막힘')
    how = f"저장된 LLM 답 재사용(판정 {out['reused_from']}){' · 입력 해시 없는 옛 답' if out.get('legacy_reuse') else ''}" if out.get('reused_from') else 'Claude 호출'
    print(f'{head} → {lv} ({where}) · {how}')
    if isinstance(blocked, int) or blocked == 'personal_scope':
        keys = ['personal_scope'] if blocked == 'personal_scope' else [c for c, v in E.R.CONDITIONS.items() if v['level'] == blocked]
        for k in keys:
            v = out['final'][k]
            if v['status'] != 'met': print(f"  막힌 조건 {k} {v['kind']}: {v['status']} — {v['note'] or v['reason']}")
    statuses = [v['status'] for k, v in out['final'].items() if k != 'personal_scope']
    lowered = sum(1 for k, v in out['final'].items() if v['note'])
    print(f"  31개 조건: 충족 {statuses.count('met')} · 미충족 {statuses.count('not_met')} · 근거 부족 {statuses.count('unknown')} · "
          f"충돌 {statuses.count('conflict')} (규칙으로 내린 것 {lowered}) · 재검토 {out['retries']}회 · 추정 비용 ${cost:.3f}")
    if out['omitted']: print(f"  길이 제한으로 뺀 파일 {len(out['omitted'])}개: {', '.join(out['omitted'][:5])}{' …' if len(out['omitted']) > 5 else ''}")


def estimate(target, fx, files, docs, cached_repos):
    """글자 수로 어림한 호출 1회 비용(코드·한글 섞임, 3자 ≈ 1토큰). 실제 실행 때는 호출마다 count_tokens로 다시 센다."""
    (shared, tail), shown, omitted = E.bundle(target, fx, files, docs)
    key = (target['repo'], target['sha'])
    rate = E.PRICE['cache_read'] if key in cached_repos else E.PRICE['cache_write']
    cached_repos.add(key)
    head = len(E.system_prompt()) / 2.5 + len(shared) / 3
    return (head * rate + len(tail) / 3 * E.PRICE['cache_write'] + 12_000 * E.PRICE['output']) / 1e6, len(shown) - 1, len(omitted)


def main():
    p = argparse.ArgumentParser(description='기술 찾기 → 판정(규칙 먼저, 필요할 때만 Claude API) → 내 STAT')
    p.add_argument('url', help='https://github.com/<계정> 또는 계정 이름')
    p.add_argument('--skills', help='평가할 기술만 쉼표로(예: Python,JavaScript)')
    p.add_argument('--min-own-lines', type=int, default=50, help='본인 줄이 이보다 적은 기술은 평가하지 않음(제안)')
    p.add_argument('--budget-usd', type=float, default=3.0, help='이번 실행에서 쓸 수 있는 최대 추정 비용')
    p.add_argument('--model', default=E.MODEL, choices=list(E.PRICES), help=f'판정 모델(기본 {E.MODEL})')
    p.add_argument('--effort', default=E.EFFORT, choices=['low', 'medium', 'high', 'xhigh', 'max'], help=f'추론 강도(기본 {E.EFFORT})')
    p.add_argument('--shadow-rate', type=float, default=0.2,
                   help='규칙만으로 끝난 판정 중 Claude까지 돌려 비교할 비율(제안 0.2, 정답 세트 계정은 1 권장)')
    p.add_argument('--dry-run', action='store_true', help='Claude를 부르지 않고 대상·판정 방식·예상 비용만 출력')
    p.add_argument('--fresh', action='store_true', help='같은 입력의 저장된 LLM 답이 있어도 Claude를 다시 부름')
    p.add_argument('--reuse-legacy', action='store_true', help='입력 해시가 없는 옛 판정(같은 계정·레포·commit·기술·모델)의 답도 다시 씀(그 답이 본 파일로만 검사)')
    p.add_argument('--repos', help='이 레포만 판정(쉼표로, 예: openmath2/OpenMath)')
    p.add_argument('--db', type=Path, default=HERE / 'out' / 'github.sqlite')
    p.add_argument('--cache', type=Path, default=extract.CACHE_DIR)
    a = p.parse_args()
    try: login = extract.parse_login(a.url)
    except ValueError as e: p.error(str(e))
    E.configure(a.model, a.effort)
    store.require_consent(a.db, login, readonly=a.dry_run)  # 동의가 없거나 철회된 계정은 Claude에 보내지 않는다
    run, all_repos = load(a.db, login)
    index, _ = S.load_dictionary()
    only = {x.strip().lower() for x in a.skills.split(',')} if a.skills else None
    repos = [r for r in all_repos if r['full_name'].lower() in {x.strip().lower() for x in a.repos.split(',')}] if a.repos else all_repos
    chosen, skipped = targets(repos, a.cache, index, a.min_own_lines, only)
    ver = versions()
    print(f"계정 {run['login']} · 추출 실행 {run['id']}({run['started_at']}) · 평가 대상 {len(chosen)}개 · 제외 {len(skipped)}개 · "
          f"규칙 {ver['rule_version']}({ver['rule_hash'][:8]}) · 사전 {ver['dict_version']} · 모델 {E.MODEL}(effort {E.EFFORT})")
    for tech, repo, ev, s, _, reason in skipped: print(f"  제외: {tech} · {repo['full_name']} ({reason})")
    if a.dry_run:
        total, cached_repos = 0.0, set()
        for tech, repo, ev, s, path, _ in chosen:
            target, files, docs = materials(tech, repo, ev, s, path)
            fx, flags = facts(repo, ev, repo['own_commits'])
            ih = E.input_hash(target, fx, files, docs)
            lines, how = [], None
            for shadow in (False, True):
                if shadow and not (how == 'rule_only' and (shadow_pick(target, a.shadow_rate) or plan(
                        a.db, run.get('account_id'), target, fx, flags, files, docs, ih, a, True, readonly=True)[0] == 'cache')): continue
                how, found = plan(a.db, run.get('account_id'), target, fx, flags, files, docs, ih, a, shadow, readonly=True)
                label = '그림자 ' if shadow else ''
                if how == 'no_material': lines.append('판정 안 함(보여 줄 코드 없음) $0')
                elif how == 'rule_only': lines.append('규칙만(실행 기록 없음) $0')
                elif how == 'cache': lines.append(f"{label}저장된 답(판정 {found['id']}{', 입력 해시 없는 옛 답' if found['legacy'] else ''}) $0")
                else:
                    est, n_shown, n_omit = estimate(target, fx, files, docs, cached_repos)
                    total += est
                    lines.append(f'{label}Claude 호출 ${est:.2f}(파일 {n_shown}개 표시 · {n_omit}개 뺌)')
            print(f"  {tech:10s} {repo['full_name']} {ev['branches']} · " + ' · '.join(lines))
        print(f"합계 예상 ${total:.2f}(출력 1.2만 토큰 가정) · 최악(출력 {E.MAX_TOKENS // 1000}K 토큰) 기준은 실제 실행 때 호출마다 확인")
        return
    claude = Claude(a.budget_usd)
    E.RAW_DIR = a.db.parent / 'llm'
    stop = False
    for tech, repo, ev, s, path, _ in chosen:
        target, files, docs = materials(tech, repo, ev, s, path)
        fx, flags = facts(repo, ev, repo['own_commits'])
        ih = E.input_hash(target, fx, files, docs)
        for shadow in (False, True):
            # 그림자 실행: 표본으로 뽑혔거나, 같은 입력의 저장된 답이 있으면(비용 0) 붙여서 LLM 해석을 남긴다
            if shadow and not (out.get('mode') == 'rule_only' and (shadow_pick(target, a.shadow_rate) or plan(
                    a.db, run.get('account_id'), target, fx, flags, files, docs, ih, a, True)[0] == 'cache')): continue
            try: res = judge_one(claude, a.db, run.get('account_id'), (repo, ev, s, path), target, fx, flags, files, docs, ih, a, shadow)
            except Exception as e:  # 한 기술이 실패해도 나머지는 계속한다. 비용을 낸 응답은 RAW_DIR에 이미 남아 있다
                print(f"\n■ {tech} · {repo['full_name']}{' 그림자' if shadow else ''} → 오류 {type(e).__name__}: {str(e)[:300]}"); break
            aid = store.save_assessment(a.db, run['id'], res, extract.now(), E.MODEL, E.EFFORT, versions=ver,
                                        shadow_of=official if shadow else None, review=review_reasons(res))
            report(res)
            if not shadow: out, official = res, aid
            if res['status'] == 'budget': print('  예산 한도에 닿아 멈춥니다. --budget-usd를 올려 다시 실행하세요'); stop = True; break
        if stop: break
    report_stat(a, run, all_repos, index, ver)
    print(f'\n이번 실행 추정 비용 ${claude.budget.spent:.3f} / 예산 ${a.budget_usd:.2f} · 저장: {a.db}')


def report_stat(a, run, all_repos, index, ver):
    """STAT 분모는 이 추출 실행의 판정 대상 전체(필터 없이)와 이미 판정한 기술이다. 판정하지 못한 기술은 미확인으로 센다.
    기술을 나눠 돌려도 기술별 현재 판정(is_current)을 모두 합치고, 기술 LV는 레포별 LV 중 최고다. 그림자 실행은 세지 않는다."""
    expected = {tech for tech, *_ in targets(all_repos, a.cache, index, a.min_own_lines, None)[0]}
    db = store.connect(a.db)
    rows = db.execute("SELECT id, tech, level, in_dictionary FROM assessment WHERE run_id = ? AND is_current = 1 AND status = 'ok' "
                      "AND mode != 'shadow' ORDER BY id", (run['id'],)).fetchall()
    db.close()
    best, ids, known = {tech: -1 for tech in expected}, {}, {}
    for aid, tech, level, in_dict in rows:
        best[tech] = max(best.get(tech, -1), -1 if level is None else level)
        ids.setdefault(tech, []).append(aid)
        if in_dict is not None: known[tech] = bool(in_dict)
    levels = {k: (None if v < 0 else v) for k, v in best.items()}
    missing = sorted(expected - set(ids))
    if levels:
        st = E.stat(levels)
        note = '핵심 기술 목록(직무 기준표 v1)이 미정이라 이 추출 실행의 판정 대상과 이미 판정한 기술을 모두 분모로 씀(제안)'
        if missing: note += f" · 판정 못 한 기술 {len(missing)}개는 미확인으로 셈: {', '.join(missing)}"
        techs = [dict(tech=t, level=levels[t], in_dictionary=known.get(t), assessment_ids=ids.get(t, [])) for t in levels]
        store.save_stat(a.db, run['id'], extract.now(), levels, st, note, techs, ver)
        print(f"\n내 STAT · 기술 {st['n']}개: " + ', '.join(f"{k} {'미확인' if v is None else f'LV{v}'}" for k, v in levels.items()))
        print('  ' + ' · '.join(f'{E.STAGES[k]} {r:.0%}' for k, r in enumerate(st['reach'])))
        print(f"  막힌 단계: {E.STAGES[st['blocked']] if st['blocked'] is not None else '없음'} → 유형: {st['type']} (기준 {st['threshold']:.0%}, {note})")


if __name__ == '__main__': main()
