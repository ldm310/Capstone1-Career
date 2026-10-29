"""내 STAT 화면(FE 미리보기)에 넘길 JSON을 만든다. DB는 읽기만 하고 Claude는 부르지 않는다(비용 0).

화면은 숫자를 계산하지 않고 이 파일 값을 그대로 보여 준다. 도달률·막힌 단계·유형은 저장된 STAT 값이고, 두 가지를 다시 확인해 함께 남긴다:
저장된 판정으로 기술별 LV와 STAT을 다시 계산해도 같은지, 저장된 LLM 판단에 지금 규칙을 다시 적용해도(rejudge.py와 같은 방식, 저장 안 함) 같은지.
막힌 이유 묶음, 「필요한 자료」 문구, 화면 구성은 제안이다.
"""
import argparse
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path

import assess as A
import engine as E
import extract
import rejudge
import rubric_source as R
import skills as S
import store

HERE = Path(__file__).resolve().parent
LEVEL_NAMES = {c['level']: c['stage'] for c in R.CONDITIONS.values()}
OFFLINE = E.OFFLINE
RESULT = {'success': '성공', 'failure': '실패', 'cancelled': '취소', 'skipped': '건너뜀', 'timed_out': '시간 초과', 'neutral': '중립',
          'action_required': '승인 필요', 'startup_failure': '시작 실패', 'stale': '오래됨'}
KIND_RULES = {  # engine.check()의 유형별 인정 규칙을 화면용으로 줄인 설명(규칙 자체가 제안)
    '문서형': '보여 준 자료(문서·코드·FACTS)에서 원문 그대로 인용해야 인정',
    '코드형': '본인이 마지막으로 쓴 줄(git blame)의 코드를 12자 이상 인용해야 인정(한글 등은 2자로 셈)',
    '실행 기록형': '같은 commit에 성공한 실행 기록(Actions·check run)이 있고 그 기록을 인용해야 인정. 실패만 있으면 충족 불가',
    '활용 기록형': '이슈 기록이 있고 그 기록을 인용해야 인정(배포만으로는 안 됨)',
    '혼합': '문서형과 같은 인용 검사(원문 일치)만 함. 어떤 근거를 함께 볼지는 LLM 해석',
    '개인 기여': '본인 줄의 코드를 인용해야 인정. 아니면 LV 자체가 미확인(실험 규칙)'}
OPEN = [  # 화면에 「제안」「미정」으로 함께 보여 줄 항목(HANDOFF.md 4·7·11장)
    ('제안', 'STAT 계산: 도달률(k) = LV ≥ k인 기술 수 ÷ N, 미확인은 미도달로 셈, LV4·5는 「개선·설계」로 묶음'),
    ('제안', '막힌 단계 기준값 50%와 지원자 유형 이름'),
    ('미정', '분모 N: 핵심 기술 목록(직무 기준표 v1)이 없어 이번 추출 실행의 판정 대상과 이미 판정한 기술을 모두 씀'),
    ('미정', '평가 시점 commit: 지금은 기술마다 본인 줄이 가장 많은 commit(제안)'),
    ('제안', '조건 유형별 인정 규칙(코드형·실행 기록형·활용 기록형·개인 기여)과 「기술 LV = 프로젝트별 LV 중 최고」'),
    ('제안', '위험 8개와 「적용 여부를 모르면 LV2 이상 보류」(실험 규칙, 확정 아님)'),
    ('제안', '개인 기여 관문: 충족이 아니면 LV 미확인(실험 코드 level_of에서 가져옴)'),
    ('미정', '실행 기록이 없을 때 테스트 workflow 안내 여부 · 「필요한 자료」 문구는 제안'),
    ('미정', '누적형 LV2 상한(실제 활용 기록이 없으면 LV2에서 멈춤)을 받아들일지'),
    ('미정', '이 화면을 FE에 넣을지와 위치, 옛 「분석 결과」 탭의 LV 1~100 점수와 이름이 겹치는 문제'),
    ('제안', '그림자 실행 비율(기본 0.2, 정답 세트를 만들 계정은 1)과 표본을 고르는 방식(레포·commit·기술 해시로 고정)')]


def rows(db, sql, args=()):
    cur = db.execute(sql, args)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def base(note): return (note or '').replace(OFFLINE, '').split(E.HOLD)[0] or None


def item_view(r, key):
    return dict(id=r[key], llm_status=r['llm_status'], status=r['final_status'], reason=r['reason'], rule_note=r['rule_note'],
                evidence=json.loads(r['evidence'] or '[]'), lowered=r['llm_status'] is not None and r['llm_status'] != r['final_status'])


def root_of(db, a):
    """reused_from을 따라가 실제로 LLM을 부른 판정을 찾는다(재사용·규칙 재적용 행은 비용 0)."""
    cur = a
    while cur['reused_from']:
        cur = rows(db, 'SELECT * FROM assessment WHERE id = ?', (cur['reused_from'],))[0]
    return cur


def workflows(path, sha):
    r = subprocess.run(['git', '-C', str(path), 'ls-tree', '-r', '--name-only', sha, '.github/workflows'], capture_output=True, text=True)
    return [p for p in r.stdout.split() if p.endswith(('.yml', '.yaml'))]


def blocked_label(level, blocked):
    if blocked is None: return 'LV5까지 막힘 없음'
    if blocked == 'personal_scope': return '개인 기여가 확인되지 않아 LV 미확인'
    if blocked == 'risk': return f'위험 적용 여부를 몰라 LV2 이상 보류(실험 규칙) · 지금 LV{level}'
    return f'LV{blocked} {LEVEL_NAMES[int(blocked)]}에서 막힘'


def label_of(cid):
    return f'위험: {E.RISKS[cid]}' if cid in E.RISKS else '개인 기여' if cid == 'personal_scope' else cid


def need_of(kind, rule, ctx):
    """막힌 항목에 필요한 자료(제안 문구). 근거 자체가 없는 경우, LLM 판단이 규칙에 걸린 경우, LLM 해석으로 모자란 경우를 나눈다."""
    branch = (ctx['branches'] or '').replace(',', '·')
    if rule == E.NO_RETRY[0]:
        return (f"평가 commit과 같은 commit에서 성공한 실행 기록(GitHub Actions·check run). 지금 평가 commit {ctx['sha'][:7]}({branch})에는 없음. "
                f'테스트를 돌리는 workflow를 넣고 평가 commit이 있는 {branch} 브랜치에 새 commit을 올리면 그 commit부터 기록이 생김(평가 commit 규칙은 미정)')
    if rule == E.NO_RETRY[1] or (kind == '실행 기록형' and not ctx['ran'] and ctx['failed']):
        return '같은 commit에서 성공한 실행 기록(지금은 실패한 기록만 있음)'
    if rule == E.NO_RETRY[2]: return '이 기능을 실제로 쓰면서 생긴 문제·요청을 남긴 이슈 기록'
    head = '추가 자료는 필요 없음. 규칙 검사에 걸린 LLM 판단(인용 문제·근거 충돌)'
    retry = {'hold': f'{head}이 추가 LLM 재검토(최대 3회)로도 풀리지 않아 승급 보류',
             'offline': f'{head}. 규칙만 다시 적용한 결과라 추가 LLM 재검토는 아직 안 함(assess.py --fresh로 다시 판정)',
             'target': f'{head}이라 추가 LLM 재검토 대상(풀리지 않으면 승급 보류)',
             'skip': f'{head}이지만, 같은 단계의 다른 조건이 먼저 풀려야 LV가 올라서 재검토하지 않음'}
    if ctx['retry']: return retry[ctx['retry']]
    if kind == '실행 기록형':
        return ('실행 기록이 이 기술의 동작을 확인했다는 근거(무엇을 실행·검사했는지)'
                + (f". 판정 때 workflow 파일({', '.join(ctx['unseen'])})을 보여 주지 않아 다시 판정하면 달라질 수 있음" if ctx['unseen'] else ''))
    return {'코드형': '본인 줄에 있는 이 기술의 구현 코드', '활용 기록형': '실제 사용 중 생긴 문제·요청을 남긴 이슈 기록',
            '혼합': '문서 근거와 코드·실행 근거', '개인 기여': '본인이 쓴 줄(git blame)에 있는 이 기술의 코드',
            'risk': '이 위험이 과제에 해당하는지 판단할 근거'}.get(kind, '요구·위험·대안 등을 적은 문서(README·이슈·PR 설명)')


def blockers_of(a, final, risks, ctx):
    """막힌 단계에서 충족으로 확인되지 않은 항목. 원인은 규칙 메모(근거 자체가 없음 등)가 있으면 그것, 없으면 LLM 해석 결과다."""
    blocked = a['blocked_at']
    if blocked is None: return []
    if blocked == 'risk': items = [(r['id'], 'risk', r) for r in risks if r['status'] == 'unknown']
    elif blocked == 'personal_scope': items = [('personal_scope', '개인 기여', final['personal_scope'])]
    else: items = [(c, final[c]['kind'], final[c]) for c, v in R.CONDITIONS.items() if v['level'] == int(blocked) and final[c]['status'] != 'met']
    # 규칙만으로 판정해 LLM이 보지 않은 조건은 막힌 조건이 아니라 아직 판단하지 않은 조건이다
    items = [(c, k, v) for c, k, v in items if base(v['rule_note']) != E.RULE_ONLY]
    # 저장된 판정에서 엔진이 재검토로 고를 항목(engine.retry_targets). 재검토 문구를 실제 동작에 맞춘다
    like = lambda v: dict(status=v['status'], llm_status=v['llm_status'], note=base(v['rule_note']))
    targets = E.retry_targets({k: like(v) for k, v in final.items()}, {r['id']: like(r) for r in risks})
    out = []
    for cid, kind, v in items:
        rule, raw = base(v['rule_note']), v['rule_note'] or ''
        retry = (None if rule in E.NO_RETRY or not (rule or v['status'] == 'conflict')
                 else 'hold' if E.HOLD in raw else 'offline' if OFFLINE in raw else 'target' if cid in targets else 'skip')
        out.append(dict(id=cid, label=label_of(cid), kind=kind, status=v['status'], llm_status=v['llm_status'],
                        cause=rule or {'unknown': '근거 부족', 'not_met': '미충족', 'conflict': '근거 충돌'}[v['status']],
                        by='규칙' if rule else 'LLM 해석', reason=v['reason'], need=need_of(kind, rule, dict(ctx, retry=retry))))
    return out


def rule_check(db, a, repo, ev, path, found):
    """저장된 LLM 판단에 지금 규칙을 다시 적용해(저장하지 않음) 저장된 판정과 같은지 본다. 규칙만으로 끝난 판정은 규칙만 다시 적용한다.
    재검토 꼬리표(→ 승급 보류 · 재검토 필요(오프라인))는 빼고, 상태와 원인 메모만 비교한다."""
    if found is None: return dict(same=None, same_level=None, note='clone이나 평가 commit이 없어 다시 계산하지 못함', diffs=[])
    if a['tech'] not in found: return dict(same=False, same_level=None, note='지금 기술 찾기에서 이 기술이 나오지 않아 다시 계산하지 못함', diffs=[])
    out = rejudge.rejudge_one(db, (a['id'], a['tech'], a['shown_files'], a['mode']), repo, ev, found[a['tech']], path)
    if out is None: return dict(same=False, same_level=False, note='같은 commit의 실행 기록이 생겨 Claude 판정이 필요함(assess.py)', diffs=[])
    stored = {r['cond_id']: r for r in rows(db, 'SELECT * FROM finding WHERE assessment_id = ?', (a['id'],))}
    stored |= {r['risk_id']: r for r in rows(db, 'SELECT * FROM risk_item WHERE assessment_id = ?', (a['id'],))}
    # 끝내 못 푼 충돌을 엔진은 unknown으로, rejudge는 conflict + 오프라인 꼬리표로 남긴다. 같은 뜻이므로 맞춰서 비교한다
    norm = lambda st, note: ('unknown' if st == 'conflict' and OFFLINE in (note or '') else st, base(note))
    diffs = [dict(id=k, stored=stored[k]['final_status'] if k in stored else None, now=v['status'], now_note=base(v['note']))
             for k, v in {**out['final'], **out['risks']}.items()
             if k not in stored or norm(v['status'], v['note']) != norm(stored[k]['final_status'], stored[k]['rule_note'])]
    blocked = None if out['blocked'] is None else str(out['blocked'])
    same_level = out['level'] == a['level'] and blocked == a['blocked_at']
    lv = '미확인' if out['level'] is None else f"LV{out['level']}"
    note = (None if same_level and not diffs else f'지금 규칙으로 다시 계산하면 조건 {len(diffs)}개가 달라짐(LV·막힌 곳은 같음)' if same_level
            else f'지금 규칙으로는 {lv} · {blocked_label(out["level"], blocked)}')
    return dict(same=same_level and not diffs, same_level=same_level, note=note, diffs=sorted(diffs, key=lambda d: d['id']))


def assessment_view(db, a, repo, ev, cache, index):
    path = cache / a['repo'].replace('/', '__')
    found = {r['cond_id']: dict(item_view(r, 'cond_id'), kind=r['kind']) for r in rows(db, 'SELECT * FROM finding WHERE assessment_id = ?', (a['id'],))}
    for cid, c in R.CONDITIONS.items(): found[cid].update(level=c['level'], condition=c['condition'], hint=c['evidence'])
    risk_rows = {r['risk_id']: r for r in rows(db, 'SELECT * FROM risk_item WHERE assessment_id = ?', (a['id'],))}
    risks = [dict(item_view(risk_rows[k], 'risk_id'), label=label) for k, label in E.RISKS.items()]
    shown = json.loads(a['shown_files'] or '[]')
    ran, failed = A.run_flags(ev) if ev else (False, False)
    cloned = bool(repo and ev and (path / '.git').exists())
    unseen = ([w for w in workflows(path, a['sha']) if w not in shown]
              if cloned and a['mode'] != 'rule_only' and (ev['actions'] or ev['check_runs']) else [])  # LLM을 부르지 않았으면 해당 없음
    skills = S.detect(path, a['sha'], [dict(path=p, lines=r) for p, r in ev['units'].items()], index)['skills'] if cloned else None
    root = root_of(db, a)
    own = repo['own_commits'] if repo else (0, 0, 0)
    details = json.loads((ev or {}).get('run_details') or 'null') or {}
    counts = {s: sum(found[c]['status'] == s for c in R.CONDITIONS) for s in E.FINDING_STATES}
    check = rule_check(db, a, repo, ev, path, skills)
    shadow = (rows(db, "SELECT * FROM assessment WHERE shadow_of = ? AND status = 'ok' ORDER BY id DESC LIMIT 1", (a['id'],)) or [None])[0]
    if shadow:  # 그림자 실행: LLM은 충족이라 했는데 규칙이 막은 조건(규칙이 너무 엄격한지 볼 신호). LV에는 반영하지 않는다
        sf = rows(db, 'SELECT cond_id, llm_status, final_status, rule_note FROM finding WHERE assessment_id = ?', (shadow['id'],))
        shadow = dict(id=shadow['id'], level=shadow['level'], blocked_label=blocked_label(shadow['level'], shadow['blocked_at']),
                      judged_at=shadow['created_at'], reused_from=shadow['reused_from'],
                      met=sum(f['final_status'] == 'met' for f in sf if f['cond_id'] != 'personal_scope'),
                      llm_met_rule_blocked=[dict(id=f['cond_id'], note=base(f['rule_note'])) for f in sf
                                            if f['llm_status'] == 'met' and f['final_status'] != 'met'])
    blockers = blockers_of(a, found, risks, dict(sha=a['sha'], branches=ev['branches'] if ev else None, ran=ran, failed=failed, unseen=unseen))
    now = {d['id']: d['now'] for d in check['diffs']}
    for b in blockers: b['now'] = now.get(b['id'])  # 지금 규칙으로 다시 계산하면 바뀌는 상태(같으면 None)
    return dict(
        id=a['id'], tech=a['tech'], repo=a['repo'], sha=a['sha'], branches=ev['branches'] if ev else None,
        level=a['level'], blocked_at=a['blocked_at'], blocked_label=blocked_label(a['level'], a['blocked_at']),
        mode=a['mode'], shadow=shadow, review_reasons=json.loads(a['review_reasons'] or '[]'),
        in_dictionary=None if a['in_dictionary'] is None else bool(a['in_dictionary']),
        counts=dict(counts, lowered=sum(found[c]['lowered'] for c in R.CONDITIONS)),
        personal_scope=found['personal_scope'],
        levels=[dict(level=n, name=LEVEL_NAMES[n], met=sum(found[c]['status'] == 'met' for c, v in R.CONDITIONS.items() if v['level'] == n),
                     conditions=[found[c] for c, v in R.CONDITIONS.items() if v['level'] == n]) for n in range(6)],
        risks=risks, blockers=blockers,
        facts=dict(own_lines=ev['own_lines'], total_lines=ev['own_lines'] + ev['other_lines'] + ev['name_only_lines'],
                   tech_own_lines=(skills or {}).get(a['tech'], {}).get('own_lines'),
                   own_commits=own[0], own_added=own[1],
                   one_commit_share=round(own[2] / own[1], 2) if own[1] and own[2] >= 100 and own[2] / own[1] >= 0.8 else None,
                   actions=ev['actions'], check_runs=ev['check_runs'], ran=ran, run_failed=failed,
                   runs=[f"{r['name']} → {RESULT.get(r['conclusion'], r['conclusion'])}" for r in details.get('workflow_runs', [])]
                   + [f"{c['name']} → {RESULT.get(c['conclusion'], c['conclusion'])}" for c in details.get('check_runs', [])],
                   issues=repo['issues'], pulls=repo['pulls'], pulls_merged=repo['pulls_merged'], deployments=repo['deployments']) if ev else None,
        # 길이 제한으로 뺀 파일은 LLM을 부른 원래 판정에 남아 있다(규칙 재적용 행은 비어 있음)
        materials=dict(shown=len(shown), omitted=json.loads(root['omitted_files'] or '[]'), unseen_workflows=unseen),
        judged=dict(llm_id=root['id'] if a['mode'] != 'rule_only' else None, llm_at=root['created_at'], model=root['model'], effort=root['effort'],
                    retries=root['retries'],
                    cost_usd=root['cost_usd'], row_at=a['created_at'], reused=a['id'] != root['id'],
                    rule_version=a['rule_version'], rule_hash=a['rule_hash'], dict_version=a['dict_version']),
        rule_check=check)


def repo_views(db, run_id, items, skipped):
    out = []
    for r in rows(db, 'SELECT * FROM repo WHERE run_id = ? ORDER BY id', (run_id,)):
        evs = rows(db, 'SELECT sha, branches, own_lines, name_only_lines, other_lines, actions, check_runs FROM eval_commit WHERE repo_id = ? '
                       'ORDER BY own_lines DESC', (r['id'],))
        techs = sorted({x['tech'] for x in items if x['repo'] == r['full_name']}, key=str.lower)
        own, name_only = max((e['own_lines'] or 0 for e in evs), default=0), max((e['name_only_lines'] or 0 for e in evs), default=0)
        low = [f"{t} {s['own_lines']:,}줄" for t, rp, _, s, _, _ in skipped if rp['full_name'] == r['full_name']]
        reason = (r['error'] or (None if techs else f'이름만 일치하는 commit만 있음(이메일이 계정에 연결되지 않음, {name_only:,}줄) → 추정이라 제외'
                  if not own and name_only else '본인 줄 없음(다른 사람의 줄만 있음)' if not own
                  else f"기술별 본인 줄이 기준(제안) 미만: {', '.join(low)}" if low else f'본인 줄 {own:,}줄에서 평가할 기술을 찾지 못함'))
        out.append(dict(name=r['full_name'], source=r['source'], default_branch=r['default_branch'], techs=techs, excluded=reason,
                        diverged=r['develop_contains_main'] == 0, issues=r['issues'], pulls=r['pulls'], actions_all=r['actions_all'],
                        evals=[dict(sha=e['sha'], branches=e['branches'], own_lines=e['own_lines'], total_lines=(e['own_lines'] or 0)
                                    + (e['other_lines'] or 0) + (e['name_only_lines'] or 0), actions=e['actions'], check_runs=e['check_runs'])
                               for e in evs]))
    return out


def blocker_groups(items):
    """레포 × 평가 commit × 원인 × 막힌 항목 묶음이 같은 기술끼리 묶는다(기술마다 막힌 조건이 다르면 다른 묶음)."""
    groups = {}
    for x in items:
        by_cause = {}
        for b in x['blockers']: by_cause.setdefault(b['cause'], []).append(b)
        for cause, bs in by_cause.items():
            labels = [b['label'] for b in bs]
            g = groups.setdefault((x['repo'], x['sha'], cause, tuple(labels)), dict(
                repo=x['repo'], sha=x['sha'], branches=x['branches'], cause=cause, by=bs[0]['by'], conditions=labels, statuses=[],
                techs=[], needs=[], unseen=x['materials']['unseen_workflows'], now_met=True, same_level=True))
            g['techs'].append(x['tech'])
            for b in bs:
                g['statuses'] += [b['status']] if b['status'] not in g['statuses'] else []
                g['needs'] += [b['need']] if b['need'] not in g['needs'] else []
                g['now_met'] &= b['now'] == 'met'  # 묶음 전체가 지금 규칙으로는 충족이면, 이전 규칙 때문에 생긴 묶음이다
            g['same_level'] &= x['rule_check']['same_level'] is True
    return list(groups.values())


def export(db_path, cache, login, min_own):
    store.require_consent(db_path, login, readonly=True)
    run, repos = A.load(db_path, login)  # 끝까지 마친 최신 추출 실행(읽기 전용으로 연다)
    missing = [r['full_name'] for r in repos if r['evals'] and not (cache / r['full_name'].replace('/', '__') / '.git').exists()]
    if missing: raise SystemExit(f"clone 캐시가 없습니다: {', '.join(missing)} (--cache를 확인하거나 check_github.py를 다시 실행하세요)")
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    st = (rows(db, 'SELECT * FROM stat WHERE run_id = ? ORDER BY id DESC LIMIT 1', (run['id'],)) or [None])[0]
    if not st: raise SystemExit(f"추출 실행 {run['id']}의 STAT이 DB에 없습니다. 먼저 assess.py나 rejudge.py를 실행하세요")
    # STAT이 쓴 판정: stat_tech.assessment_ids. v1 STAT에는 그 기록이 없어, 저장할 때와 같은 방식(그 시점까지 기술 × 레포마다 최신 판정)으로 고른다
    used = [r['assessment_ids'] and json.loads(r['assessment_ids']) for r in rows(db, 'SELECT assessment_ids FROM stat_tech WHERE stat_id = ?', (st['id'],))]
    if used and all(u is not None for u in used):
        ids = sorted({i for u in used for i in u})
        latest = rows(db, f"SELECT * FROM assessment WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id", ids) if ids else []
    else:
        latest = rows(db, "SELECT * FROM assessment WHERE id IN (SELECT MAX(id) FROM assessment WHERE run_id = ? AND status = 'ok' "
                          "AND mode != 'shadow' AND created_at <= ? GROUP BY tech, repo) ORDER BY id", (run['id'], st['created_at']))
    index, _ = S.load_dictionary()
    rule_now = A.rule_hash()
    by_repo = {r['full_name']: r for r in repos}
    items = []
    for a in latest:
        repo = by_repo.get(a['repo'])
        ev = next((e for e in (repo or {}).get('evals', []) if e['sha'] == a['sha']), None)
        items.append(assessment_view(db, a, repo, ev, cache, index))
    chosen, skipped = A.targets(repos, cache, index, min_own, None)
    levels = json.loads(st['levels'])
    best = {}
    for x in items: best[x['tech']] = max(best.get(x['tech'], -1), -1 if x['level'] is None else x['level'])
    again = E.stat(levels, st['threshold'] if st['threshold'] is not None else 0.5)
    reach = json.loads(st['reach'])
    n = len(levels)
    target_set, judged = {t for t, *_ in chosen}, set(best)
    techs = sorted(({'name': t, 'level': lv, 'assessments': [x['id'] for x in items if x['tech'] == t],
                     'in_dictionary': next((x['in_dictionary'] for x in items if x['tech'] == t and x['in_dictionary'] is not None), None)}
                    for t, lv in levels.items()), key=lambda t: (t['level'] is None, -(t['level'] or 0), t['name'].lower()))
    repo_list = repo_views(db, run['id'], items, skipped)
    db.close()
    return dict(
        version=1, generated_at=extract.now(),
        source=dict(db=str(Path(db_path).resolve().relative_to(HERE.parent)) if Path(db_path).resolve().is_relative_to(HERE.parent) else str(db_path),
                    login=run['login'], run_id=run['id'], run_started_at=run['started_at'], api_calls=run['api_calls'], stat_id=st['id']),
        stat=dict(created_at=st['created_at'], n=n, threshold=again['threshold'], blocked=st['blocked_at'], type=st['type'], note=st['note'],
                  n_basis=(f'이번 추출 실행의 판정 대상(지금 기술 찾기 기준) {len(target_set)}개와 이미 판정한 기술 {len(judged)}개를 합친 {n}개. '
                           '판정하지 못한 대상은 미확인으로 셈'),
                  blocked_stage=None if st['blocked_at'] is None else E.STAGES[st['blocked_at']],
                  stages=[dict(k=k, name=name, reached=sum(lv is not None and lv >= k for lv in levels.values()), ratio=reach[k])
                          for k, name in enumerate(E.STAGES)]),
        types=[dict(blocked=E.STAGES[k] if k is not None else '막힘 없음', type=t) for k, t in E.TYPES.items()],
        level_names={str(k): v for k, v in LEVEL_NAMES.items()}, kind_rules=KIND_RULES,
        not_accepted={k: v for k, v in R.NOT_ACCEPTED.items()}, open=[dict(state=s, text=t) for s, t in OPEN],
        techs=techs, assessments=items, blockers=blocker_groups(items), repos=repo_list,
        checks=dict(  # 저장된 값과 다시 계산한 값이 같은지(화면 맨 아래 개발 확인용에 보여 준다)
            stat_same=again['reach'] == reach and again['blocked'] == st['blocked_at'] and again['type'] == st['type'],
            threshold_source='STAT 표에 저장된 기준값' if st['threshold'] is not None else 'STAT 표에 기준값이 없어 engine.stat 기본값(0.5)을 씀',
            # STAT에 있지만 판정이 없는 기술은 미확인으로 센다(assess.report_stat)
            levels_same=judged <= set(levels) and all((None if best.get(t, -1) < 0 else best[t]) == lv for t, lv in levels.items()),
            # STAT 분모는 지금의 판정 대상 ∪ 이미 판정한 기술(assess.report_stat). 기술 찾기가 바뀌면 둘이 어긋날 수 있다
            denominator_same=len(target_set | judged) == n,
            targets_now=len(target_set),
            judged_not_target=[dict(tech=t, why=next((why for t2, _, _, _, _, why in skipped if t2 == t), '지금 기술 찾기에서 나오지 않음'))
                               for t in sorted(set(levels) - target_set, key=str.lower)],
            target_not_judged=sorted(target_set - judged, key=str.lower),
            rules_same=sum(x['rule_check']['same'] is True for x in items), rules_total=len(items),
            rule_now=dict(version=E.RULE_VERSION, hash=rule_now),
            rule_stale=[dict(tech=x['tech'], repo=x['repo'], version=x['judged']['rule_version']) for x in items if x['judged']['rule_hash'] != rule_now],
            modes=dict(Counter(x['mode'] for x in items)), shadows=sum(x['shadow'] is not None for x in items),
            llm_calls=len({x['judged']['llm_id'] for x in items if x['judged']['llm_id'] is not None}),
            llm_cost_usd=round(sum({x['judged']['llm_id']: x['judged']['cost_usd'] or 0 for x in items if x['judged']['llm_id'] is not None}.values()), 3)))


def main():
    p = argparse.ArgumentParser(description='내 STAT 미리보기용 JSON 내보내기(DB 읽기 전용, 비용 0)')
    p.add_argument('url', help='https://github.com/<계정> 또는 계정 이름')
    p.add_argument('--db', type=Path, default=HERE / 'out' / 'github.sqlite')
    p.add_argument('--cache', type=Path, default=HERE / '.cache' / 'repos')
    p.add_argument('--min-own-lines', type=int, default=50, help='assess.py와 같은 값(판정 대상·제외 목록 계산용)')
    p.add_argument('--out', type=Path, default=HERE / 'out' / 'stat_view.json')
    a = p.parse_args()
    view = export(a.db, a.cache, extract.parse_login(a.url), a.min_own_lines)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_suffix('.tmp')
    tmp.write_text(json.dumps(view, ensure_ascii=False, indent=1))
    tmp.replace(a.out)  # 화면이 쓰는 도중의 파일을 읽지 않게 한 번에 바꾼다
    st, ck = view['stat'], view['checks']
    print(f"내 STAT(id {view['source']['stat_id']}) · 기술 {st['n']}개 · " + ' · '.join(f"{s['name']} {s['reached']}/{st['n']}" for s in st['stages']))
    print(f"  막힌 단계 {st['blocked_stage'] or '없음'} → {st['type']} · 판정 {len(view['assessments'])}개 · 막힌 이유 묶음 {len(view['blockers'])}개")
    print(f"  다시 계산: STAT {'같음' if ck['stat_same'] else '다름'} · 기술별 LV {'같음' if ck['levels_same'] else '다름'} · "
          f"분모 {'같음' if ck['denominator_same'] else '다름'} · 지금 규칙 {ck['rules_same']}/{ck['rules_total']} 같음")
    for j in ck['judged_not_target']: print(f"  ! {j['tech']}: 이미 판정해 분모에 있지만 지금은 판정 대상 아님({j['why']})")
    if ck['target_not_judged']: print(f"  ! 판정 대상인데 판정이 없음(미확인으로 셈): {', '.join(ck['target_not_judged'])}")
    for x in view['assessments']:
        if x['rule_check']['same'] is not True:
            print(f"  ! {x['tech']} · {x['repo']}: {x['rule_check']['note']} "
                  + ', '.join(f"{d['id']} {d['stored']}→{d['now']}" for d in x['rule_check']['diffs']))
    print(f'  저장: {a.out}')


if __name__ == '__main__': main()
