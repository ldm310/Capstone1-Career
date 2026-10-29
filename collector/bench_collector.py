"""수집기(흐름 1~2단계) 벤치마크.

A. 합성 케이스: 정답을 구성으로 정한 로컬 git 레포 10개로 본인 commit·본인 줄 판정 방식을 비교한다. 네트워크를 쓰지 않는다.
B. DB 저장: 합성 레포를 분석해 저장한 뒤 다시 읽어 행 수·줄 수가 같은지 본다. 네트워크를 쓰지 않는다.
C. 실제 계정(--login): 빈 캐시로 여러 번 추출해 시간·API 호출·재실행 일치를 재고, 알려진 값과 대조한다.
   토큰은 ~/.config/career-stat/github.env의 GITHUB_TOKEN(career-stat-bot)에서만 읽는다(환경 변수는 보지 않는다). 없으면 아무것도 하지 않고 멈춘다.
A의 정답은 합성이라 실제 사용자 정확도가 아니다. git blame 자체의 정확도는 재지 않는다(정답도 blame으로 만든다).
"""
import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

import extract as g
import gitenv
import store

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out' / 'bench'
ME, MATE, LOGIN = 'Dongmin Lee', 'Seoyeon Park', 'me-login'
ME_MAIL, ME_LAPTOP, MATE_MAIL, TWIN_MAIL = 'me@example.com', 'me.laptop@example.com', 'mate@example.com', 'twin@example.com'
TRUE_ME = {ME_MAIL, ME_LAPTOP}  # 정답: 노트북 이메일도 본인이다
SEEN = {ME_MAIL}                # 시스템이 아는 것: 계정에 연결된 이메일뿐
NAMES = {ME, LOGIN}
GIT = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false']
# 04-repo/REMOTE_STATE.md (2026-10-27 21:41 조회) 값. 그 뒤 바뀌었을 수 있다.
KNOWN = {'ldm310': dict(repos={'ldm310/2026ESWContest_free_Ieum', 'ldm310/Auto-Reply', 'ldm310/Capstone1-Career', 'ldm310/LangGraph'},
                        repo='ldm310/Capstone1-Career', head='f3708a7',
                        activity=dict(pulls=4, pulls_merged=0, issues=0, deployments=0, actions_all=0))}


def text(tag, n, start=0): return ''.join(f'{tag} line {i}\n' for i in range(start, start + n))


class Src:
    """정답을 아는 원본 레포. 날짜를 고정해서 매번 같은 SHA가 나온다."""
    def __init__(self, root):
        self.path, self.t = root / 'src', 1_760_000_000
        subprocess.run([*GIT, 'init', '-q', '-b', 'main', str(self.path)], check=True, capture_output=True, env=gitenv.env())

    def _git(self, *args, who=None):
        env = gitenv.env()  # 사용자 git 설정과 분리. 작성자는 아래 환경 변수로만 정한다
        if who:
            self.t += 60
            env = {**env, 'GIT_AUTHOR_NAME': who[0], 'GIT_AUTHOR_EMAIL': who[1], 'GIT_COMMITTER_NAME': who[0],
                   'GIT_COMMITTER_EMAIL': who[1], 'GIT_AUTHOR_DATE': f'@{self.t} +0900', 'GIT_COMMITTER_DATE': f'@{self.t} +0900'}
        subprocess.run([*GIT, '-C', str(self.path), *args], check=True, capture_output=True, env=env)

    def commit(self, who, files):
        for p, body in files.items():
            (self.path / p).parent.mkdir(parents=True, exist_ok=True)
            (self.path / p).write_text(body)
        self._git('add', '-A')
        self._git('commit', '-q', '-m', 'work', who=who)
        return self

    def branch(self, name): self._git('checkout', '-q', '-b', name, 'main'); return self
    def checkout(self, name): self._git('checkout', '-q', name); return self
    def merge(self, name, who): self._git('merge', '--no-ff', '-q', '-m', f'merge {name}', name, who=who); return self
    def squash(self, name, who, files): self._git('merge', '--squash', name); return self.commit(who, files)

    def clone(self):
        self.checkout('main')
        dst = self.path.parent / 'clone'
        subprocess.run([*GIT, 'clone', '-q', str(self.path), str(dst)], check=True, capture_output=True, env=gitenv.env())
        return dst


me, laptop, mate, twin = (ME, ME_MAIL), (ME, ME_LAPTOP), (MATE, MATE_MAIL), (ME, TWIN_MAIL)
CASES = {
    'C1 혼자 작업': lambda s: s.commit(me, {'app.py': text('app', 20)}).commit(me, {'util.py': text('util', 10)}),
    'C2 팀원과 파일 분담': lambda s: s.commit(me, {'api.py': text('api', 20)}).commit(mate, {'db.py': text('db', 30)}),
    'C3 팀원이 내 코드를 고침': lambda s: s.commit(me, {'svc.py': text('svc', 30)}).commit(mate, {'svc.py': text('fix', 20) + text('svc', 10, 20)}),
    'C4 연결 안 된 이메일(본인)': lambda s: s.commit(me, {'a.py': text('a', 10)}).commit(laptop, {'b.py': text('b', 20)}),
    'C5 동명이인(다른 사람)': lambda s: s.commit(me, {'a.py': text('a', 10)}).commit(twin, {'c.py': text('c', 25)}),
    'C6 생성 파일 포함': lambda s: s.commit(me, {'app.js': text('js', 15), 'package-lock.json': text('lock', 400), 'dist/bundle.js': text('bundle', 300)}),
    'C7 병합 안 한 feature': lambda s: s.commit(me, {'main.py': text('m', 10)}).branch('feature/x').commit(me, {'x.py': text('x', 40)}),
    'C8 main·develop 갈라짐': lambda s: s.commit(mate, {'base.py': text('base', 10)}).branch('develop').commit(me, {'feat.py': text('feat', 30)})
                                         .checkout('main').commit(mate, {'hotfix.py': text('hot', 5)}),
    'C9 한 번에 올린 commit': lambda s: s.commit(me, {f'mod{i}.py': text(f'mod{i}', 40) for i in range(5)}).commit(me, {'mod0.py': text('mod0', 40) + text('fix', 5)}),
    'C10 남의 브랜치를 내가 병합': lambda s: s.commit(me, {'README.md': text('readme', 3)}).branch('feature/y').commit(mate, {'y.py': text('y', 40)})
                                            .checkout('main').merge('feature/y', me),
}


# 내 미완성 브랜치(40줄)를 팀원이 가져가 앞 5줄만 고쳐 main에 올린다. 정답: 내가 쓴 줄 중 남은 35줄.
MINE = lambda s: s.commit(mate, {'README.md': text('readme', 3)}).branch('feature/me').commit(me, {'feature.py': text('feat', 40)})
EDIT = {'feature.py': text('fix', 5) + text('feat', 35, 5)}
INTEGRATION = {
    'I1 내 브랜치를 이어받아 고친 뒤 병합(이력 유지)': lambda s: MINE(s).commit(mate, EDIT).checkout('main').merge('feature/me', mate),
    'I2 squash 병합 후 고침': lambda s: MINE(s).checkout('main').squash('feature/me', mate, EDIT),
    'I3 내 코드를 복사해 새 commit': lambda s: MINE(s).checkout('main').commit(mate, EDIT),
}


def build(name, root):
    src = Src(root)
    (CASES.get(name) or INTEGRATION[name])(src)
    path = src.clone()
    heads = {b: sha for b in ('main', 'develop') if (sha := g.ref(path, b))}
    log = [r.split('\0') for r in g.git(path, 'log', '--format=%H%x00%ae%x00%an', *[f'refs/remotes/origin/{b}' for b in heads]).splitlines()]
    return path, heads, log


def added(path, sha):
    """commit만 보는 방식: 첫 부모 대비 추가 줄 수(병합 commit도 그대로 센다)."""
    parents = g.git(path, 'rev-list', '--parents', '-n', '1', sha).split()[1:]
    out = g.git(path, 'diff', '--numstat', parents[0], sha) if parents else g.git(path, 'show', '--numstat', '--format=', sha)
    return sum(int(a) for a, *_ in (row.split('\t') for row in out.splitlines() if row) if a != '-')


def run_case(name, root):
    path, heads, log = build(name, root)
    truth = {sha for sha, mail, _ in log if mail in TRUE_ME}
    kinds, _ = g.own_commits(path, [f'refs/remotes/origin/{b}' for b in heads], {sha for sha, mail, _ in log if mail in SEEN}, set(SEEN), NAMES)
    pred = {'이름 일치': {sha for sha, _, name in log if name in NAMES},
            '계정 연결(현재)': {sha for sha, k in kinds.items() if k != 'name_only'},
            '계정 연결 + 이름 추정': set(kinds)}
    all_branches = {r.split('\0')[0] for r in g.git(path, 'log', '--all', '--format=%H%x00%ae').splitlines() if r.split('\0')[1] in TRUE_ME}
    stats = [x for x in g.commit_stats(path, pred['계정 연결(현재)']) if not x['merge']]
    total = sum(x['added'] for x in stats)
    diff = sum(added(path, sha) for sha in pred['계정 연결(현재)'])
    lines, generated = [], 0
    for b, sha in heads.items():
        t, _ = g.blame(path, sha, TRUE_ME, set())
        o, units = g.blame(path, sha, set(SEEN), NAMES)
        generated += sum(u['path'] == 'package-lock.json' or u['path'].startswith('dist/') for u in units)
        lines.append(dict(head=b, truth=t['own'], blame=o['own'], diff=diff))
    return dict(case=name, truth=truth, pred=pred, outside_scope=len(all_branches - truth), lines=lines, generated_units=generated,
                own_added=total, biggest_share=round(max(x['added'] for x in stats) / total, 2) if total else None)


def synthetic():
    t0 = time.monotonic()
    results = []
    for name in CASES:
        with tempfile.TemporaryDirectory() as tmp: results.append(run_case(name, Path(tmp)))
    seconds = time.monotonic() - t0
    print('\n[A] 합성 케이스 (정답은 구성으로 정함 · 실제 사용자 정확도 아님)')
    print('| 케이스 | 정답 commit | 현재 방식 | 이름 일치 | 평가 commit | 정답 줄 | blame(현재) | commit 추가 줄 합 | 비고 |')
    print('|---|---|---|---|---|---|---|---|---|')
    for r in results:
        note = [f'feature에만 있는 본인 commit {r["outside_scope"]}개 제외'] if r['outside_scope'] else []
        if r['own_added'] >= 100 and r['biggest_share'] >= 0.8: note.append(f'대량 업로드 표시: 한 commit이 본인 추가 줄의 {r["biggest_share"]:.0%}(기준 미정)')
        if r['generated_units']: note.append('생성 파일이 증거에 섞임')
        for i, x in enumerate(r['lines']):
            head = [r['case'], len(r['truth']), len(r['pred']['계정 연결(현재)']), len(r['pred']['이름 일치'])] if i == 0 else ['', '', '', '']
            print('| ' + ' | '.join(map(str, [*head, x['head'], x['truth'], x['blame'], x['diff'], '; '.join(note) if i == 0 else ''])) + ' |')
    summary = dict(seconds=round(seconds, 2), commits={}, lines={})
    print('\n| commit 판정 방식 | 정밀도 | 재현율 | 남의 commit을 본인으로 | 본인 commit을 놓침 |')
    print('|---|---|---|---|---|')
    for m in ('이름 일치', '계정 연결(현재)', '계정 연결 + 이름 추정'):
        tp = sum(len(r['pred'][m] & r['truth']) for r in results)
        fp = sum(len(r['pred'][m] - r['truth']) for r in results)
        fn = sum(len(r['truth'] - r['pred'][m]) for r in results)
        summary['commits'][m] = dict(precision=round(tp / (tp + fp), 3), recall=round(tp / (tp + fn), 3), fp=fp, fn=fn)
        print(f'| {m} | {tp / (tp + fp):.0%} | {tp / (tp + fn):.0%} | {fp} | {fn} |')
    rows = [x for r in results for x in r['lines']]
    print('\n| 본인 줄 계산 방식 | 정답과 같은 행 | 많게 센 줄 합 | 적게 센 줄 합 |')
    print('|---|---|---|---|')
    for key, label in (('blame', '평가 commit blame(현재)'), ('diff', 'commit 추가 줄 합(commit만 보는 방식)')):
        over = sum(max(x[key] - x['truth'], 0) for x in rows)
        under = sum(max(x['truth'] - x[key], 0) for x in rows)
        same = sum(x[key] == x['truth'] for x in rows)
        summary['lines'][key] = dict(exact=same, rows=len(rows), over=over, under=under)
        print(f'| {label} | {same}/{len(rows)} | {over} | {under} |')
    print(f'\n합성 케이스 {len(CASES)}개 · {seconds:.1f}초')
    dump = [dict(r, truth=len(r['truth']), pred={k: len(v) for k, v in r['pred'].items()}) for r in results]
    (OUT / 'synthetic.json').write_text(json.dumps(dict(summary=summary, cases=dump), ensure_ascii=False, indent=2) + '\n')


def integration():
    print('\n[A-2] 팀원이 내 미완성 브랜치 코드를 main에 올린 경우 (정답: 내가 쓴 40줄 중 팀원이 안 고친 35줄)')
    print('| 상황 | 정답 | blame(현재)이 잡은 본인 줄 |')
    print('|---|---|---|')
    got = {}
    for name in INTEGRATION:
        with tempfile.TemporaryDirectory() as tmp:
            path, heads, _ = build(name, Path(tmp))
            got[name] = g.blame(path, heads['main'], set(SEEN), NAMES)[0]['own']
        print(f'| {name} | 35 | {got[name]} |')
    (OUT / 'integration.json').write_text(json.dumps(dict(expected=35, got=got), ensure_ascii=False, indent=2) + '\n')


def storage():
    """합성 레포 2개를 extract.analyze_repo로 분석해 저장하고, 다시 읽어 행 수·줄 수를 맞춘다."""
    with tempfile.TemporaryDirectory() as tmp:
        res = dict(login=LOGIN, github_id=None, token=False, started_at='-', finished_at='-', api_calls=0, stopped=None,
                   identity=dict(emails=[g.mask(ME_MAIL)], names=len(NAMES)), external_pr_repos=[], repos=[], evidence=[])
        for name in ('C3 팀원이 내 코드를 고침', 'C8 main·develop 갈라짐'):
            path, heads, log = build(name, Path(tmp) / name.split()[0])
            local, units = g.analyze_repo(path, heads, {sha for sha, mail, _ in log if mail in SEEN}, set(SEEN), NAMES)
            full = f'synthetic/{name.split()[0]}'
            res['repos'].append(dict(full=full, fork=False, default_branch='main', size_kb=0, heads=heads,
                                     activity=dict(pulls=0, pulls_merged=0, pulls_own=0, issues=0, deployments=0, actions_all=0), **local))
            res['evidence'] += [dict(repo=full, **u) for u in units]
        db = Path(tmp) / 'bench.sqlite'
        account = store.add_account(db, LOGIN, '본인', '합성 벤치마크 계정(실제 사람 아님)', '2026-10-28')
        got = store.counts(db, store.save(db, res, account))
    want = dict(repo=len(res['repos']), own_commit=sum(len(r['commits']) for r in res['repos']),
                eval_commit=sum(len(r['evals']) for r in res['repos']), evidence_line=sum(len(u['lines']) for u in res['evidence']),
                evidence_lines_total=sum(e - s + 1 for u in res['evidence'] for s, e in u['lines']),
                own_lines_total=sum(e['own'] for r in res['repos'] for e in r['evals'].values()))
    print('\n[B] DB 저장 확인 (합성 레포 2개 → SQLite → 다시 읽기)')
    print('| 항목 | 넣은 값 | 다시 읽은 값 | 일치 |')
    print('|---|---|---|---|')
    for k in want: print(f"| {k} | {want[k]} | {got[k]} | {'예' if want[k] == got[k] else '아니오'} |")
    print(f"본인 줄 요약 = 증거 단위 줄 합: {'예' if got['own_lines_total'] == got['evidence_lines_total'] else '아니오'}")
    (OUT / 'storage.json').write_text(json.dumps(dict(want=want, got=got), ensure_ascii=False, indent=2) + '\n')


def real(url, runs, token):
    login = g.parse_login(url)
    store.require_consent(HERE / 'out' / 'github.sqlite', login, readonly=True)  # 실제 계정은 동의 기록이 있을 때만 잰다
    volatile = ('started_at', 'finished_at', 'api_calls', 'rate_remaining')
    measured = []
    with tempfile.TemporaryDirectory() as tmp:
        for _ in range(runs):
            t0 = time.monotonic()
            res = g.extract(login, token, Path(tmp) / 'repos')
            measured.append(dict(seconds=round(time.monotonic() - t0, 1), api_calls=res['api_calls'], stopped=res['stopped'], res=res))
            if res['stopped']: break
    first = measured[0]['res']
    strip = lambda r: {k: v for k, v in r.items() if k not in volatile}
    same = len(measured) == runs and all(strip(m['res']) == strip(first) for m in measured)
    print(f"\n[C] 실제 계정 {first['login']} (토큰 {'있음' if first['token'] else '없음'})")
    print('| 실행 | 캐시 | 시간 | API 호출 | 중단 |')
    print('|---|---|---|---|---|')
    for i, m in enumerate(measured):
        print(f"| {i + 1} | {'빈 캐시(clone)' if i == 0 else 'clone 재사용(fetch)'} | {m['seconds']}초 | {m['api_calls']}회 | {m['stopped'] or '없음'} |")
    done = [r for r in first['repos'] if 'activity' in r]
    print(f"레포 {len(first['repos'])}개 · 본인 commit {sum(c['kind'] != 'name_only' for r in done for c in r['commits'])}개 · "
          f"본인 줄 {sum(e['own'] for r in done for e in r['evals'].values())}줄 · 재실행 결과 {'같음' if same else '다름'}")
    checks, known = {}, KNOWN.get(first['login'])
    if known:
        repo = next((r for r in done if r['full'] == known['repo']), None)
        checks['공개 레포 목록'] = {r['full'] for r in first['repos']} == known['repos']
        checks[f"{known['repo']} main·develop commit"] = bool(repo) and all(sha.startswith(known['head']) for sha in repo['heads'].values())
        for k, v in known['activity'].items(): checks[f"{known['repo']} {k}={v}"] = bool(repo) and repo['activity'][k] == v
        print('알려진 값(2026-10-27 조회)과 대조: ' + ' · '.join(f"{k} {'일치' if ok else '다름'}" for k, ok in checks.items()))
    (OUT / 'real.json').write_text(json.dumps(dict(login=first['login'], rerun_same=same, known_checks=checks,
                                                   runs=[{k: v for k, v in m.items() if k != 'res'} for m in measured]),
                                              ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description='수집기(흐름 1~2단계) 벤치마크')
    p.add_argument('--login', help='실제 계정 측정(C)까지 할 때 계정 URL 또는 이름. ~/.config/career-stat/github.env의 GITHUB_TOKEN 필요')
    p.add_argument('--runs', type=int, default=2)
    a = p.parse_args()
    token = None
    if a.login:  # 합성 측정(A·B)도 돌리기 전에 확인한다
        try: token = gitenv.github_token()
        except gitenv.TokenError as e: p.error(str(e))
    OUT.mkdir(parents=True, exist_ok=True)
    synthetic()
    integration()
    storage()
    if a.login: real(a.login, a.runs, token)
    print(f'\n저장: {OUT}')


if __name__ == '__main__': main()
