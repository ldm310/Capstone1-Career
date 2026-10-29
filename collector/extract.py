"""GitHub 데이터 추출 (흐름 1~2단계).

공개 레포(상한 없음) → main·develop 계열의 본인 commit → 평가 commit의 본인 줄 → 실행·활용 기록을 결과 하나(dict)로 돌려준다.
GET 요청과 git 읽기만 한다. 사용자 코드는 실행하지 않는다. 출력은 check_github.py, 저장은 store.py가 맡는다.
모든 git 호출은 gitenv 환경(사용자 git 설정과 분리)으로 돈다. 레포는 checkout 없는 부분 clone으로 받는다.
"""
import http.client
import json
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
import pydriller
from git.exc import GitError

import gitenv
from paths import HEAD_BYTES, generated, line_count, skipped

API = 'https://api.github.com'
TLS = ssl.create_default_context(cafile=certifi.where())
CACHE_DIR = Path(__file__).resolve().parent / '.cache' / 'repos-v2'  # checkout 없는 부분 clone. 옛 캐시(.cache/repos, checkout 있음)는 쓰지 않는다
CLONE_FILTER = 'blob:limit=512k'  # 이 크기 이상인 blob은 받지 않는다. paths.MAX_BLOB과 같아서 그런 파일은 어차피 세지 않는다
BRANCHES = ('main', 'master', 'develop', 'dev', 'develope')  # 기본 브랜치와 함께 보는 브랜치(결정 9번, dev·develope는 2026-10-29 결정)
SEARCH_PAGES = 10  # 검색 API가 주는 최대: 100개씩 10쪽 = 1,000개(그 뒤 쪽은 422)
ENV = gitenv.env()  # 읽기용 git 환경(토큰 없음)
LIST_ENV = {**ENV, 'GIT_NO_LAZY_FETCH': '1'}  # ls-tree -l용: 부분 clone이 받지 않은 blob을 크기 보느라 내려받지 않는다(크기 칸이 BAD)
# github.com/<이 이름>은 계정이 아니라 GitHub 화면 주소다. 같은 이름의 다른 계정을 분석하지 않도록 막는다.
RESERVED = {'dashboard', 'settings', 'notifications', 'explore', 'orgs', 'organizations', 'marketplace', 'pulls', 'issues',
            'topics', 'trending', 'login', 'logout', 'signup', 'new', 'codespaces', 'sponsors', 'features', 'about',
            'pricing', 'enterprise', 'search', 'stars', 'apps', 'copilot'}


class StopCheck(RuntimeError): pass


class RateLimited(StopCheck):
    """한도 초과가 기다렸다 다시 해도(Api.TRIES번) 풀리지 않음. 레포 단위 호출이면 extract가 그 레포만 미확인으로 둔다."""


class CacheError(RuntimeError):
    """clone 캐시를 쓸 수 없음(작업 트리가 있는 옛 방식 clone). 그 레포만 실패로 둔다."""


class Api:
    """GitHub REST GET. 토큰은 Authorization 머리말로만 보낸다.
    ETag가 온 응답은 etag_cache에 두고 다음 요청에 If-None-Match를 보낸다. 304면 캐시한 본문을 쓴다(304는 한도에 안 세므로 calls에도 안 센다).
    한도 초과(403·429에 Retry-After가 있거나 X-RateLimit-Remaining이 0)는 풀릴 때까지, 5xx와 연결 실패는 잠깐 기다렸다 다시 한다(모두 합쳐 TRIES번).
    그래도 안 되면 StopCheck를 던진다(한도면 RateLimited). sleep·clock·opener는 시험에서 바꿔 끼운다."""
    TRIES = 3

    def __init__(self, token, opener=urllib.request.urlopen, etag_cache=None, *, sleep=time.sleep, clock=time.time):
        self.token, self.calls, self.remaining = token, 0, None
        self.opener, self.etags, self.sleep, self.clock = opener, {} if etag_cache is None else etag_cache, sleep, clock

    def _send(self, url):
        """요청 한 번 → (상태, 본문, 머리말). urllib은 304·4xx·5xx를 HTTPError로 던지지만 여기서는 응답으로 돌려준다."""
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'career-stat-collector'}
        if self.token: headers['Authorization'] = f'Bearer {self.token}'
        if url in self.etags: headers['If-None-Match'] = self.etags[url][0]
        try:
            with self.opener(urllib.request.Request(url, headers=headers), timeout=30, context=TLS) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            with e: return e.code, e.read(), e.headers

    def _limit_wait(self, status, h):
        """한도 초과면 기다릴 초, 아니면 None. 2차 한도는 Retry-After만큼, 1차 한도는 X-RateLimit-Reset(epoch 초)까지 + 1초(최대 1시간)."""
        if status not in (403, 429): return None
        after, reset = h.get('Retry-After'), h.get('X-RateLimit-Reset')
        if after: return int(after) if after.isdigit() else 60
        if h.get('X-RateLimit-Remaining') != '0': return None  # 한도와 상관없는 403(권한 등)은 다시 하지 않는다
        return min(max(int(reset) - self.clock(), 0), 3600) + 1 if reset and reset.isdigit() else 60

    def _open(self, url, ok):
        where = url.split('?')[0]
        for attempt in range(1, self.TRIES + 1):
            try: status, body, h = self._send(url)
            except (OSError, http.client.HTTPException) as e:  # 응답 없음: 연결 실패·시간 초과
                if attempt == self.TRIES: raise StopCheck(f'GET {where} → 연결 실패({type(e).__name__})') from e
                self.sleep(2 ** (attempt - 1)); continue
            self.remaining = h.get('X-RateLimit-Remaining', self.remaining)
            if status == 304 and url in self.etags:  # 바뀌지 않음: 캐시한 본문과 다음 쪽 링크를 그대로 쓴다
                _, body, link = self.etags[url]
                return (json.loads(body) if body else None), ({'Link': link} if link else {}), 200
            self.calls += 1
            wait = self._limit_wait(status, h)
            if wait is None and status >= 500: wait = 2 ** (attempt - 1)
            if wait is not None:
                if attempt < self.TRIES: self.sleep(wait); continue
                if status in (403, 429): raise RateLimited(f'GET {where} → API 한도 소진(HTTP {status}, {self.TRIES}번 시도)')
            if status not in ok: raise StopCheck(f'GET {where} → HTTP {status}')
            if status == 200 and h.get('ETag'): self.etags[url] = (h['ETag'], body, h.get('Link'))
            return (json.loads(body) if body and status == 200 else None), h, status  # 404·409 같은 허용 상태는 값이 없다

    def get(self, path, params=None, ok=(200,)):
        return self._open(API + path + ('?' + urllib.parse.urlencode(params) if params else ''), ok)

    def pages(self, path, params, max_pages=10, key=None):
        """목록 API를 Link 머리말의 다음 쪽을 따라 읽는다. max_pages=None이면 끝까지 읽는다.
        key는 본문에서 목록이 든 칸이다(검색 API는 {"items": [...]}를 준다)."""
        url, n = API + path + '?' + urllib.parse.urlencode(params), 0
        while url and (max_pages is None or n < max_pages):
            data, h, status = self._open(url, (200, 409))  # 409 = 빈 레포
            if status == 409: return
            yield from ((data or {}).get(key) if key else data) or []
            nxt = re.search(r'<([^>]+)>;\s*rel="next"', h.get('Link') or '')
            url, n = nxt and nxt.group(1), n + 1


def parse_login(url):
    m = re.fullmatch(r'(?:https?://)?(?:www\.)?(?:github\.com/)?([A-Za-z0-9][A-Za-z0-9-]{0,38})/?', url.strip())
    if not m: raise ValueError('GitHub 계정 URL이 아닙니다')
    if m.group(1).lower() in RESERVED:
        raise ValueError(f'github.com/{m.group(1)}는 계정 주소가 아닙니다. https://github.com/<계정 이름> 형식으로 넣어 주세요')
    return m.group(1)


def git(path, *args, timeout=120, env=None):
    """git 명령 하나(출력은 글자로). env를 주지 않으면 읽기용 ENV로 돈다."""
    return subprocess.run(['git', '-C', str(path), *args], capture_output=True, encoding='utf-8', errors='replace',
                          env=env or ENV, timeout=timeout, check=True).stdout


def sync(full, cache, token, url=None):
    """레포를 캐시에 받는다: checkout 없는 부분 clone(512KiB 이상 blob은 받지 않음, 태그 없음). 이미 받았으면 fetch --prune만 한다.
    checkout이 없어야 레포에 심은 .mailmap 파일이 작성자를 바꾸지 못한다. 작업 트리가 있는 캐시(옛 방식 clone)는 쓰지도 지우지도 않는다(CacheError).
    토큰은 gitenv가 환경 변수의 HTTP 헤더로만 넘긴다(URL·명령줄·.git/config에 남지 않음). url은 시험에서 file:// 원격으로 바꿔 끼운다."""
    path = Path(cache) / full.replace('/', '__')
    env = gitenv.env(token)
    if (path / '.git').exists():
        if (path / '.git' / 'index').exists() or any(p.name != '.git' for p in path.iterdir()):
            raise CacheError(f'캐시 {path.name}에 checkout(작업 트리)이 있어 쓰지 않음')
        git(path, 'fetch', '--quiet', '--prune', '--no-tags', 'origin', timeout=600, env=env)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        git(path.parent, 'clone', '--quiet', '--no-checkout', f'--filter={CLONE_FILTER}', '--no-tags',
            url or f'https://github.com/{full}.git', str(path), timeout=600, env=env)
    return path


def ref(path, branch):
    r = subprocess.run(['git', '-C', str(path), 'rev-parse', '--verify', '--quiet', f'refs/remotes/origin/{branch}^{{commit}}'],
                       capture_output=True, text=True, env=ENV)
    return r.stdout.strip() or None


def branch_heads(path, default):
    """평가할 브랜치와 그 끝 commit: 기본 브랜치, main(없으면 master), develop·dev·develope(있는 것 모두). 기본 브랜치가 맨 앞이다."""
    main = next((b for b in BRANCHES[:2] if ref(path, b)), None)
    return {b: sha for b in dict.fromkeys([default, main, *BRANCHES[2:]]) if b and (sha := ref(path, b))}


def contains(path, older, newer):
    return subprocess.run(['git', '-C', str(path), 'merge-base', '--is-ancestor', older, newer], capture_output=True, env=ENV).returncode == 0


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
    """본인 commit의 줄 수(PyDriller). lock·빌드 결과 같은 생성 파일은 빼고 센다.
    PyDriller가 부르는 git(GitPython)에도 ENV를 덮어쓴다. GitPython은 os.environ을 복사한 뒤 덮어쓰므로 ENV는 자격 증명 경로를 빈 값으로 막아 둔다.
    부분 clone이 받지 않은 큰 blob은 diff를 만들 때 내려받는다(결과는 전체 clone과 같다). 내려받지 못하면 GitError가 난다."""
    if not shas: return []
    repo = pydriller.Git(str(path))
    repo.repo.git.update_environment(**ENV)
    try:
        out = []
        for sha in shas:
            c = repo.get_commit(sha)
            kept = [m for m in c.modified_files if not skipped(m.new_path or m.old_path, 0)]
            out.append(dict(sha=c.hash, date=c.author_date.isoformat(), added=sum(m.added_lines for m in kept),
                            deleted=sum(m.deleted_lines for m in kept), files=len(kept), merge=c.merge))
        return out
    finally: repo.clear()


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
    blob은 git cat-file 묶음으로 한 번만 읽고, 내용이 같은 파일은 읽은 것을 함께 쓴다. 돌려주는 것: {경로: (줄 수, 생성 파일인가)}.
    읽지 못한 blob(cat-file이 missing으로 답함. 부분 clone에서 내려받지 못한 경우)의 경로는 넣지 않는다: 건너뛴 파일과 같다."""
    by_blob, scanned = {}, {}
    for p, blob in entries: by_blob.setdefault(blob, []).append(p)
    blobs = sorted(by_blob)
    for k in range(0, len(blobs), chunk):
        out = subprocess.run(['git', '-C', str(path), 'cat-file', '--batch'], input=('\n'.join(blobs[k:k + chunk]) + '\n').encode(),
                             capture_output=True, env=ENV, timeout=600, check=True).stdout
        i = 0
        while i < len(out):
            j = out.index(b'\n', i)
            fields = out[i:j].split()
            if len(fields) != 3: i = j + 1; continue  # '<blob> missing'은 내용 없이 한 줄이다
            name, _, size = fields
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
    for entry in git(path, 'ls-tree', '-r', '-l', '-z', sha, env=LIST_ENV).split('\0'):
        if not entry: continue
        meta, p = entry.split('\t', 1)
        _, kind, blob, size = meta.split()
        # 부분 clone이 받지 않은 blob은 크기가 BAD로 나온다: 숫자와 상관없이 건너뛴다(512KiB 이상이라 paths.skipped와 같은 파일)
        if kind == 'blob' and size != 'BAD' and not skipped(p, int(size)): entries.append((p, blob))
    touches, added, reach = history(path, sha, emails, names)
    known = lambda p: p not in reach or (touches.get(p) == 1 and p in added)
    scanned = scan_blobs(path, entries)  # 후보 blob을 한 번씩만 읽는다: 줄 수(빠른 길 파일)와 생성 파일 여부(모든 파일)
    for p, _ in entries:
        if p not in scanned: continue  # 읽지 못한 blob은 누구의 줄로도 세지 않는다
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
                                  capture_output=True, env=ENV, timeout=120, check=True).stdout
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
    """clone만으로 하는 분석(API 없음): 본인 commit(PyDriller)과 평가 commit별 본인 줄(git blame).
    네트워크는 부분 clone이 받지 않은 큰 blob을 PyDriller가 diff 때 내려받을 때만 쓴다."""
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


def extract(login, token, cache, max_size_mb=None, *, api=None, remote_url=lambda full: f'https://github.com/{full}.git'):
    """계정 하나의 공개 레포를 상한 없이 모두 보고, 본인 commit이 검색된 레포를 먼저 처리한다(결과가 먼저 채워지도록).
    계정 단계 API(사용자·레포 목록·검색)가 실패하면 실행 전체를 멈춘다(res['stopped']). 레포 단위 실패(clone·API·분석)는
    그 레포의 row['error']에만 남기고 나머지는 계속한다(그 레포는 미확인). 크기로 건너뛰지 않는다(부분 clone이라 큰 파일은 받지 않는다).
    max_size_mb를 주면 그보다 큰 레포는 clone하지 않고 row['skipped']에 남긴다(실패가 아니다). api·remote_url은 시험에서 바꿔 끼운다."""
    api = Api(token) if api is None else api
    res = dict(login=login, github_id=None, token=bool(token), started_at=now(), repos=[], evidence=[], external_pr_repos=[], stopped=None)
    emails, names = set(), set()
    try:
        user, _, _ = api.get(f'/users/{login}')
        login = res['login'] = user['login']
        res['github_id'] = user['id']
        # 레포 찾기: 소유 + 멤버(collaborator·조직) + 본인 commit·PR 검색. private은 뺀다. 평가는 어디서든 main·develop 계열의 본인 줄만 한다.
        found = {}
        for kind in ('owner', 'member'):
            for r in api.pages(f'/users/{login}/repos', {'type': kind, 'per_page': 100}, max_pages=None):
                if not r['private']: found.setdefault(r['full_name'], (r, kind))
        search = lambda path, q: api.pages(path, {'q': q, 'per_page': 100}, max_pages=SEARCH_PAGES, key='items')
        commits = list(search('/search/commits', f'author:{login} is:public'))
        prs = list(search('/search/issues', f'author:{login} type:pr is:public'))
        mine = {i['repository']['full_name'] for i in commits}  # 본인 commit이 검색된 레포(검색은 기본 브랜치만 본다: 순서에만 쓴다)
        searched = mine | {i['repository_url'].split('/repos/')[1] for i in prs}
        for full in sorted(searched - set(found)):
            r, _, _ = api.get(f'/repos/{full}', ok=(200, 404))
            if r and not r['private']: found[full] = (r, 'search')
        repos = sorted(found.values(), key=lambda x: x[0]['full_name'] not in mine)  # 상한 없음. 안정 정렬이라 나머지 순서는 그대로
        res['external_pr_repos'] = sorted(full for full, (_, kind) in found.items() if kind != 'owner')

        # 1단계: clone + API로 본인 commit(계정에 연결된 것)을 먼저 모아 신원 묶음을 만든다.
        emails |= {f"{user['id']}+{login}@users.noreply.github.com".lower(), f'{login}@users.noreply.github.com'.lower()}
        if user.get('email'): emails.add(user['email'].lower())
        names.add(login)  # git 이름을 계정 이름으로 쓰는 경우가 많다. 이름 일치는 추정으로만 쓴다.
        work = []
        for r, kind in repos:
            full = r['full_name']
            row = dict(full=full, fork=r['fork'], default_branch=r['default_branch'], size_kb=r['size'], source=kind)
            res['repos'].append(row)
            if max_size_mb is not None and r['size'] > max_size_mb * 1024:
                row['skipped'] = f"레포 크기 {r['size'] // 1024}MB > {max_size_mb}MB"; continue
            try: path = sync(full, cache, token, remote_url(full))
            except subprocess.CalledProcessError: row['error'] = 'clone 실패'; continue
            except subprocess.TimeoutExpired: row['error'] = 'clone 시간 초과'; continue
            except CacheError as e: row['error'] = f'clone 캐시 문제: {e}'; continue
            heads = branch_heads(path, r['default_branch'])
            if not heads: row['error'] = '빈 레포'; continue
            api_shas = set()
            try:
                for b in heads:
                    for c in api.pages(f'/repos/{full}/commits', {'sha': b, 'author': login, 'per_page': 100}):
                        api_shas.add(c['sha']); emails.add(c['commit']['author']['email'].lower()); names.add(c['commit']['author']['name'])
            except StopCheck as e: row['error'] = f'API 실패: {e}'; continue  # 한도 소진(RateLimited)도 이 레포만 미확인
            row['heads'] = heads
            work.append((row, path, api_shas))

        # 2단계: 본인 commit·본인 줄(로컬) → 실행·활용 기록(API)
        for row, path, api_shas in work:
            try: local, units = analyze_repo(path, row['heads'], api_shas, emails, names)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, GitError) as e:  # 레포 하나가 실패해도 나머지는 계속한다
                row['error'] = f'분석 실패({type(e).__name__})'; continue
            row.update(local)
            res['evidence'] += [dict(repo=row['full'], **u) for u in units]
            if not any(e['own'] for e in row['evals'].values()):  # 본인 줄이 없으면 실행·활용 기록은 판정에 쓰이지 않는다 → API 아낌
                row['activity'] = dict(skipped=True); continue
            try:
                for sha, e in row['evals'].items(): e.update(run_records(api, row['full'], sha))
                row['activity'] = activity(api, row['full'], login)
            except StopCheck as err: row['error'] = f'API 실패: {err}'  # 실행·활용 기록을 모르면 판정하지 않는다(미확인)
    except StopCheck as e:
        res['stopped'] = str(e)
    res.update(finished_at=now(), api_calls=api.calls, rate_remaining=api.remaining,
               identity=dict(emails=sorted(mask(e) for e in emails), names=len(names)))
    return res
