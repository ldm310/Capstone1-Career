"""GitHub 데이터 추출 (흐름 1~2단계).

공개 레포 → main·develop의 본인 commit → 평가 commit의 본인 줄 → 실행·활용 기록을 결과 하나(dict)로 돌려준다.
GET 요청과 git 읽기만 한다. 사용자 코드는 실행하지 않는다. 출력은 check_github.py, 저장은 store.py가 맡는다.
"""
import json
import os
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
from pydriller import Repository

from paths import HEAD_BYTES, generated, line_count, skipped

API = 'https://api.github.com'
TLS = ssl.create_default_context(cafile=certifi.where())
GIT_ENV = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1'}
# github.com/<이 이름>은 계정이 아니라 GitHub 화면 주소다. 같은 이름의 다른 계정을 분석하지 않도록 막는다.
RESERVED = {'dashboard', 'settings', 'notifications', 'explore', 'orgs', 'organizations', 'marketplace', 'pulls', 'issues',
            'topics', 'trending', 'login', 'logout', 'signup', 'new', 'codespaces', 'sponsors', 'features', 'about',
            'pricing', 'enterprise', 'search', 'stars', 'apps', 'copilot'}


class StopCheck(RuntimeError): pass


class Api:
    def __init__(self, token):
        self.token, self.calls, self.remaining = token, 0, None

    def _open(self, url, ok):
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'career-stat-collector'}
        if self.token: headers['Authorization'] = f'Bearer {self.token}'
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30, context=TLS) as r:
                status, body, h = r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            status, body, h = e.code, e.read(), e.headers
        self.calls += 1
        self.remaining = h.get('X-RateLimit-Remaining', self.remaining)
        if status in (403, 429) and h.get('X-RateLimit-Remaining') == '0':
            raise StopCheck('API 한도 소진 — 토큰을 넣거나 한도가 풀린 뒤 다시 실행')
        if status not in ok: raise StopCheck(f'GET {url.split("?")[0]} → HTTP {status}')
        return (json.loads(body) if body else None), h, status

    def get(self, path, params=None, ok=(200,)):
        return self._open(API + path + ('?' + urllib.parse.urlencode(params) if params else ''), ok)

    def pages(self, path, params, max_pages=10):
        url = API + path + '?' + urllib.parse.urlencode(params)
        for _ in range(max_pages):
            data, h, status = self._open(url, (200, 409))  # 409 = 빈 레포
            if status == 409: return
            yield from data
            nxt = re.search(r'<([^>]+)>;\s*rel="next"', h.get('Link') or '')
            if not nxt: return
            url = nxt.group(1)


def parse_login(url):
    m = re.fullmatch(r'(?:https?://)?(?:www\.)?(?:github\.com/)?([A-Za-z0-9][A-Za-z0-9-]{0,38})/?', url.strip())
    if not m: raise ValueError('GitHub 계정 URL이 아닙니다')
    if m.group(1).lower() in RESERVED:
        raise ValueError(f'github.com/{m.group(1)}는 계정 주소가 아닙니다. https://github.com/<계정 이름> 형식으로 넣어 주세요')
    return m.group(1)


def git(path, *args, timeout=120):
    return subprocess.run(['git', '-C', str(path), *args], capture_output=True, encoding='utf-8', errors='replace',
                          env=GIT_ENV, timeout=timeout, check=True).stdout


def sync(full, cache):
    path = Path(cache) / full.replace('/', '__')
    if (path / '.git').exists(): git(path, 'fetch', '--quiet', '--prune', '--no-tags', 'origin', timeout=600)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--quiet', '--no-tags', f'https://github.com/{full}.git', str(path)],
                       capture_output=True, env=GIT_ENV, timeout=600, check=True)
    return path


def ref(path, branch):
    r = subprocess.run(['git', '-C', str(path), 'rev-parse', '--verify', '--quiet', f'refs/remotes/origin/{branch}^{{commit}}'],
                       capture_output=True, text=True, env=GIT_ENV)
    return r.stdout.strip() or None


def contains(path, older, newer):
    return subprocess.run(['git', '-C', str(path), 'merge-base', '--is-ancestor', older, newer], env=GIT_ENV).returncode == 0


def mask(email):
    name, _, domain = email.partition('@')
    return name[:2] + '***@' + domain


def ranges(lines):
    out = []
    for n in sorted(lines):
        if out and n == out[-1][1] + 1: out[-1][1] = n
        else: out.append([n, n])
    return out


def own_commits(path, revs, api_shas, emails, names):
    """main·develop에서 닿는 commit을 SHA 기준으로 한 번만 세고, 본인 여부를 근거별로 나눈다."""
    rows = [r.split('\0') for r in git(path, 'log', '--format=%H%x00%ae%x00%an', *revs).splitlines()]
    kinds = {}
    for sha, mail, name in rows:
        if sha in api_shas: kinds[sha] = 'api'
        elif mail.lower() in emails: kinds[sha] = 'email'
        elif name in names: kinds[sha] = 'name_only'
    return kinds, len(rows)


def commit_stats(path, shas):
    """본인 commit의 줄 수. lock·빌드 결과 같은 생성 파일은 빼고 센다."""
    out = []
    for c in Repository(str(path), include_remotes=True, only_commits=list(shas)).traverse_commits() if shas else []:
        kept = [m for m in c.modified_files if not skipped(m.new_path or m.old_path, 0)]
        out.append(dict(sha=c.hash, date=c.author_date.isoformat(), added=sum(m.added_lines for m in kept),
                        deleted=sum(m.deleted_lines for m in kept), files=len(kept), merge=c.merge))
    return out


def history(path, sha, emails, names):
    """평가 commit까지의 commit이 바꾼 경로를 git log 한 번으로 본다. blame 없이도 결과를 아는 파일을 가리기 위해서다.
    돌려주는 것: 경로별 바뀐 횟수, 한 번 추가되고 끝난 경로의 작성자 구분(own·name_only·other),
    본인·이름 일치 commit이 닿았을 수 있는 경로(이름 바꾸기를 따라가고, 같은 commit의 삭제+추가도 이름 바꾸기로 넉넉히 본다).
    작성자는 blame처럼 .mailmap을 적용한 값(%aE·%aN)으로 본다. merge commit은 어느 부모와도 다른 경로(충돌 해결)만 나온다."""
    out = git(path, 'log', '--format=%x01%aE%x02%aN', '-M', '--name-status', '-z', '--diff-merges=dense-combined', sha, timeout=600)
    touches, added, reach, moves = {}, {}, set(), []
    for rec in out.split('\x01')[1:]:
        head, _, body = rec.partition('\0')
        mail, _, name = head.partition('\x02')
        kind = 'own' if mail.lower() in emails else 'name_only' if name in names else 'other'
        tokens, i, gone, new = body.lstrip('\0\n').split('\0'), 0, [], []
        while i < len(tokens) and tokens[i]:
            status = tokens[i]
            if re.fullmatch(r'[RC]\d+', status): old, p, i = tokens[i + 1], tokens[i + 2], i + 3; moves.append(([old], [p]))
            else: p, i = tokens[i + 1], i + 2
            touches[p] = touches.get(p, 0) + 1
            if status == 'D': gone.append(p)
            elif status == 'A': new.append(p)
            if kind != 'other': reach.add(p)
        if gone and new: moves.append((gone, new))  # 이름 바꾸기로 잡히지 않은 옮김일 수 있다
        for p in new:
            if not gone: added[p] = kind  # 같은 commit에 삭제가 있으면 옮김일 수 있어 빠른 길에서 뺀다
    while True:  # 본인 경로가 옮겨 간 곳도 본인 줄이 있을 수 있다
        more = {p for olds, news in moves if reach.intersection(olds) for p in news} - reach
        if not more: return touches, added, reach
        reach |= more


def scan_blobs(path, entries, chunk=500):
    """entries [(경로, blob)]의 파일마다 줄 수(blame이 세는 방식: 마지막 줄에 줄바꿈이 없어도 한 줄)와 생성 파일 여부(paths.generated)를 구한다.
    blob은 git cat-file 묶음으로 한 번만 읽고, 내용이 같은 파일은 읽은 것을 함께 쓴다. 돌려주는 것: {경로: (줄 수, 생성 파일인가)}."""
    by_blob, scanned = {}, {}
    for p, blob in entries: by_blob.setdefault(blob, []).append(p)
    blobs = sorted(by_blob)
    for k in range(0, len(blobs), chunk):
        out = subprocess.run(['git', '-C', str(path), 'cat-file', '--batch'], input=('\n'.join(blobs[k:k + chunk]) + '\n').encode(),
                             capture_output=True, env=GIT_ENV, timeout=600, check=True).stdout
        i = 0
        while i < len(out):
            j = out.index(b'\n', i)
            name, _, size = out[i:j].split()
            body = out[j + 1:j + 1 + int(size)]
            n, head = line_count(body), body[:HEAD_BYTES]
            head_lines = n if len(body) <= HEAD_BYTES else None  # 앞부분이 파일 전체면 센 줄 수를 다시 세지 않는다
            for p in by_blob[name.decode()]: scanned[p] = (n, generated(p, head, head_lines))
            i = j + 2 + int(size)
    return scanned


def blame(path, sha, emails, names):
    """평가 commit에서 줄마다 마지막 작성자를 보고, 본인 줄을 증거 단위 {sha, path, lines}로 묶는다.
    경로·내용 필터(paths.skipped·generated)에 걸린 파일은 어디에도 세지 않는다.
    나머지는 모든 파일을 blame한 결과와 같되, 결과가 정해진 파일은 줄 수만 센다: 본인·이름 일치 commit이 닿지 않은 파일(전부 다른 사람),
    한 번 추가되고 바뀐 적 없는 파일(전부 그 commit 작성자). 커널 소스처럼 한 번에 올린 파일 수만 개도 몇 초 안에 끝난다."""
    count, units = dict(own=0, name_only=0, other=0, files=0), []
    entries = []
    for entry in git(path, 'ls-tree', '-r', '-l', '-z', sha).split('\0'):
        if not entry: continue
        meta, p = entry.split('\t', 1)
        _, kind, blob, size = meta.split()
        if kind == 'blob' and not skipped(p, int(size)): entries.append((p, blob))
    touches, added, reach = history(path, sha, emails, names)
    known = lambda p: p not in reach or (touches.get(p) == 1 and p in added)
    scanned = scan_blobs(path, entries)  # 후보 blob을 한 번씩만 읽는다: 줄 수(빠른 길 파일)와 생성 파일 여부(모든 파일)
    for p, _ in entries:
        n, is_generated = scanned[p]
        if is_generated: continue  # 빌드 결과물·SQL 덤프·minified·생성 파일은 누구의 줄로도 세지 않는다(blame도 하지 않는다)
        if known(p):
            who = added.get(p, 'other') if p in reach else 'other'
            count[who] += n
            count['files'] += 1
            if who == 'own' and n: units.append(dict(sha=sha, path=p, lines=[[1, n]]))
            continue
        # 바이트로 읽는다: 텍스트로 읽으면 Python이 혼자 있는 \r도 줄바꿈으로 바꿔 줄 수가 git과 달라진다
        try: out = subprocess.run(['git', '-C', str(path), 'blame', '-w', '--line-porcelain', sha, '--', p],
                                  capture_output=True, env=GIT_ENV, timeout=120, check=True).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired): continue
        count['files'] += 1
        mine, line, mail, author = [], None, None, None
        for row in out.split(b'\n'):
            if row.startswith(b'\t'):
                if mail in emails: count['own'] += 1; mine.append(line)
                elif author in names: count['name_only'] += 1
                else: count['other'] += 1
            elif row.startswith(b'author-mail '): mail = row[13:-1].decode('utf-8', 'replace').lower()
            elif row.startswith(b'author '): author = row[7:].decode('utf-8', 'replace')
            elif re.match(rb'[0-9a-f]{40,64} \d+ \d+', row): line = int(row.split()[2])
        if mine: units.append(dict(sha=sha, path=p, lines=ranges(mine)))
    return count, units


def analyze_repo(path, heads, api_shas, emails, names):
    """clone만으로 하는 분석(네트워크 없음): 본인 commit(PyDriller)과 평가 commit별 본인 줄(git blame)."""
    revs = [f'refs/remotes/origin/{b}' for b in heads]
    kinds, reachable = own_commits(path, revs, api_shas, emails, names)
    stats = {x['sha']: x for x in commit_stats(path, [sha for sha, k in kinds.items() if k != 'name_only'])}
    commits = [dict(sha=sha, kind=k, **{key: stats.get(sha, {}).get(key) for key in ('date', 'added', 'deleted', 'files', 'merge')})
               for sha, k in kinds.items()]
    evals, units = {}, []
    for b, sha in heads.items():
        if sha in evals: evals[sha]['branches'].append(b); continue
        count, u = blame(path, sha, emails, names)
        evals[sha] = dict(branches=[b], **count)
        units += u
    local = dict(reachable=reachable, commits=commits, evals=evals)
    first = next(iter(heads))  # 기본 브랜치
    if 'develop' in heads and first != 'develop' and heads[first] != heads['develop']:
        local['develop_contains_main'] = contains(path, f'refs/remotes/origin/{first}', 'refs/remotes/origin/develop')
    return local, units


def run_records(api, full, sha):
    """같은 commit의 실행 기록. 개수와 함께 무엇을 돌렸는지(workflow 이름·경로, check run 이름·결과)도 남긴다."""
    a, _, _ = api.get(f'/repos/{full}/actions/runs', {'head_sha': sha, 'per_page': 20}, ok=(200, 404))
    c, _, _ = api.get(f'/repos/{full}/commits/{sha}/check-runs', {'per_page': 50}, ok=(200, 404))
    s, _, _ = api.get(f'/repos/{full}/commits/{sha}/status', ok=(200, 404))
    runs, checks, statuses = (a or {}).get('workflow_runs', []), (c or {}).get('check_runs', []), (s or {}).get('statuses', [])
    return dict(actions=(a or {}).get('total_count', 0), conclusions=[r['conclusion'] for r in runs],
                check_runs=(c or {}).get('total_count', 0), statuses=(s or {}).get('total_count', 0),
                details=dict(workflow_runs=[dict(name=r.get('name'), path=r.get('path'), event=r.get('event'), conclusion=r.get('conclusion')) for r in runs],
                             check_runs=[dict(name=x.get('name'), conclusion=x.get('conclusion'), app=(x.get('app') or {}).get('slug')) for x in checks],
                             statuses=[dict(context=x.get('context'), state=x.get('state')) for x in statuses]))


def activity(api, full, login):
    pulls = list(api.pages(f'/repos/{full}/pulls', {'state': 'all', 'per_page': 100}, max_pages=3))
    issues = [i for i in api.pages(f'/repos/{full}/issues', {'state': 'all', 'per_page': 100}, max_pages=3) if 'pull_request' not in i]
    deploys = list(api.pages(f'/repos/{full}/deployments', {'per_page': 100}, max_pages=3))
    runs, _, _ = api.get(f'/repos/{full}/actions/runs', {'per_page': 1}, ok=(200, 404))
    return dict(pulls=len(pulls), pulls_merged=sum(bool(p.get('merged_at')) for p in pulls),
                pulls_own=sum((p.get('user') or {}).get('login') == login for p in pulls),
                issues=len(issues), deployments=len(deploys), actions_all=(runs or {}).get('total_count', 0))


def now(): return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def extract(login, token, cache, max_repos=30, max_size_mb=300):
    api = Api(token)
    res = dict(login=login, github_id=None, token=bool(token), started_at=now(), repos=[], evidence=[], external_pr_repos=[], stopped=None)
    emails, names = set(), set()
    try:
        user, _, _ = api.get(f'/users/{login}')
        login = res['login'] = user['login']
        res['github_id'] = user['id']
        # 레포 찾기: 소유 + 멤버(collaborator·조직) + 본인 commit·PR 검색. private은 뺀다. 평가는 어디서든 main·develop의 본인 줄만 한다.
        found = {}
        for kind in ('owner', 'member'):
            for r in api.pages(f'/users/{login}/repos', {'type': kind, 'per_page': 100}):
                if not r['private']: found.setdefault(r['full_name'], (r, kind))
        commits, _, _ = api.get('/search/commits', {'q': f'author:{login} is:public', 'per_page': 100})
        prs, _, _ = api.get('/search/issues', {'q': f'author:{login} type:pr is:public', 'per_page': 100})
        searched = {i['repository']['full_name'] for i in commits['items']} | {i['repository_url'].split('/repos/')[1] for i in prs['items']}
        for full in sorted(searched - set(found)):
            r, _, _ = api.get(f'/repos/{full}', ok=(200, 404))
            if r and not r['private']: found[full] = (r, 'search')
        repos = list(found.values())[:max_repos]
        res['external_pr_repos'] = sorted(full for full, (_, kind) in found.items() if kind != 'owner')

        # 1단계: clone + API로 본인 commit(계정에 연결된 것)을 먼저 모아 신원 묶음을 만든다.
        emails |= {f"{user['id']}+{login}@users.noreply.github.com".lower(), f'{login}@users.noreply.github.com'.lower()}
        if user.get('email'): emails.add(user['email'].lower())
        names.add(login)  # git 이름을 계정 이름으로 쓰는 경우가 많다. 이름 일치는 추정으로만 쓴다.
        work = []
        for r, kind in repos:
            row = dict(full=r['full_name'], fork=r['fork'], default_branch=r['default_branch'], size_kb=r['size'], source=kind)
            res['repos'].append(row)
            if r['size'] > max_size_mb * 1024: row['error'] = f"레포 크기 {r['size'] // 1024}MB > {max_size_mb}MB"; continue
            try: path = sync(r['full_name'], cache)
            except subprocess.CalledProcessError: row['error'] = 'clone 실패'; continue
            except subprocess.TimeoutExpired: row['error'] = 'clone 시간 초과'; continue
            # main = 기본 브랜치(결정 9번). 기본 브랜치가 main·master가 아니어도 main(없으면 master)이 있으면 함께 본다.
            main = next((b for b in ('main', 'master') if ref(path, b)), None)
            heads = {b: sha for b in dict.fromkeys([r['default_branch'], main, 'develop']) if b and (sha := ref(path, b))}
            if not heads: row['error'] = '빈 레포'; continue
            api_shas = set()
            for b in heads:
                for c in api.pages(f"/repos/{r['full_name']}/commits", {'sha': b, 'author': login, 'per_page': 100}):
                    api_shas.add(c['sha']); emails.add(c['commit']['author']['email'].lower()); names.add(c['commit']['author']['name'])
            row['heads'] = heads
            work.append((row, path, api_shas))

        # 2단계: 본인 commit·본인 줄(로컬) → 실행·활용 기록(API)
        for row, path, api_shas in work:
            try: local, units = analyze_repo(path, row['heads'], api_shas, emails, names)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:  # 레포 하나가 실패해도 나머지는 계속한다
                row['error'] = f'분석 실패({type(e).__name__})'; continue
            row.update(local)
            res['evidence'] += [dict(repo=row['full'], **u) for u in units]
            if not any(e['own'] for e in row['evals'].values()):  # 본인 줄이 없으면 실행·활용 기록은 판정에 쓰이지 않는다 → API 아낌
                row['activity'] = dict(skipped=True); continue
            for sha, e in row['evals'].items(): e.update(run_records(api, row['full'], sha))
            row['activity'] = activity(api, row['full'], login)
    except StopCheck as e:
        res['stopped'] = str(e)
    res.update(finished_at=now(), api_calls=api.calls, rate_remaining=api.remaining,
               identity=dict(emails=sorted(mask(e) for e in emails), names=len(names)))
    return res
