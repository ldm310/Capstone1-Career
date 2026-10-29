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
from datetime import datetime, timezone
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
SHA = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')  # commit SHA(SHA-1·SHA-256)
STATUS = re.compile(r'[A-Z]+[0-9]*')  # --name-status의 상태: A·D·M·T, R100·C075(경로 둘), merge의 합친 diff는 부모마다 한 글자(MM·RM, 경로 하나)
SYNCED = 'career-synced'  # clone·fetch가 끝까지 성공한 캐시에만 .git 안에 남기는 완료 표지(끊긴 clone을 가려낸다)
# github.com/<이 이름>은 계정이 아니라 GitHub 화면 주소다. 같은 이름의 다른 계정을 분석하지 않도록 막는다.
RESERVED = {'dashboard', 'settings', 'notifications', 'explore', 'orgs', 'organizations', 'marketplace', 'pulls', 'issues',
            'topics', 'trending', 'login', 'logout', 'signup', 'new', 'codespaces', 'sponsors', 'features', 'about',
            'pricing', 'enterprise', 'search', 'stars', 'apps', 'copilot'}


class StopCheck(RuntimeError): pass


class RateLimited(StopCheck):
    """한도 초과가 기다렸다 다시 해도(Api.TRIES번) 풀리지 않음. 레포 단위 호출이면 extract가 그 레포만 미확인으로 둔다."""


class CacheError(RuntimeError):
    """clone 캐시를 쓸 수 없음(작업 트리가 있는 옛 방식 clone). 그 레포만 실패로 둔다."""


class BlameError(RuntimeError):
    """git blame이 실패함(부분 clone이 받지 않은 옛 blob을 내려받지 못함, 시간 초과 등). 파일 하나를 빼고 세지 않고 그 레포를 실패로 둔다."""
    def __init__(self, path):
        super().__init__(path)
        self.path = path


class LogFormatError(ValueError):
    """git log 출력이 기대한 모양(-z, NUL 구분)이 아님. 어림잡아 읽지 않고 그 레포만 실패로 둔다(extract 2단계)."""


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

    def pages(self, path, params, max_pages=10, key=None, empty=(409,)):
        """목록 API를 Link 머리말의 다음 쪽을 따라 읽는다. max_pages=None이면 끝까지 읽는다.
        key는 본문에서 목록이 든 칸이다(검색 API는 {"items": [...]}를 준다). empty는 빈 목록으로 보는 상태다(409 = 빈 레포)."""
        url, n = API + path + '?' + urllib.parse.urlencode(params), 0
        while url and (max_pages is None or n < max_pages):
            data, h, status = self._open(url, (200, *empty))
            if status in empty: return
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
                          env=ENV if env is None else env, timeout=timeout, check=True).stdout


def sync(full, cache, token, url=None):
    """레포를 캐시에 받는다: checkout 없는 부분 clone(512KiB 이상 blob은 받지 않음, 태그 없음). 이미 받았으면 fetch --prune만 한다.
    checkout이 없어야 레포에 심은 .mailmap 파일이 작성자를 바꾸지 못한다. 작업 트리가 있는 캐시(옛 방식 clone)는 쓰지도 지우지도 않는다(CacheError).
    clone·fetch가 끝까지 성공해야 .git 안에 완료 표지(SYNCED)를 남긴다. 표지가 없는 캐시(시간 초과로 끊긴 clone 등)는
    <캐시>/.broken/<이름>-<UTC 시각>으로 옮겨 두고(지우지 않는다) 새로 clone한다. 빈 원격도 clone이 성공했으니 표지를 남긴다.
    토큰은 gitenv가 환경 변수의 HTTP 헤더로만 넘긴다(URL·명령줄·.git/config에 남지 않음). url은 시험에서 file:// 원격으로 바꿔 끼운다."""
    cache = Path(cache).absolute()  # 상대 경로면 git -C <캐시> 아래에 한 번 더 겹쳐 clone되므로 절대 경로로 바꾼다
    path, env = cache / full.replace('/', '__'), gitenv.env(token)
    if path.exists():
        if (path / '.git' / 'index').exists() or any(p.name != '.git' for p in path.iterdir()):
            raise CacheError(f'캐시 {path.name}에 checkout(작업 트리)이 있어 쓰지 않음')
        if not (path / '.git' / SYNCED).exists():  # 끝까지 받지 못한 캐시: 옮겨 두고 새로 받는다
            aside = cache / '.broken' / f'{path.name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S.%fZ}'
            try:
                aside.parent.mkdir(parents=True, exist_ok=True)
                path.rename(aside)
            except OSError as e: raise CacheError(f'끝까지 받지 못한 캐시 {path.name}를 옮기지 못함({type(e).__name__})') from e
    if path.exists(): git(path, 'fetch', '--quiet', '--prune', '--no-tags', 'origin', timeout=600, env=env)
    else:
        cache.mkdir(parents=True, exist_ok=True)
        git(cache, 'clone', '--quiet', '--no-checkout', f'--filter={CLONE_FILTER}', '--no-tags',
            url or f'https://github.com/{full}.git', str(path), timeout=600, env=env)
    (path / '.git' / SYNCED).write_text(now() + '\n')
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


def log_commits(path, revs, env=None, changes=False):
    """git log를 NUL 구분(-z)으로 한 번 읽어 commit마다 (SHA, 메일(소문자), 이름, [(상태, [경로…])])를 log 순서로 돌려준다.
    작성자는 commit에 적힌 값(%ae·%an)이다(.mailmap 미적용). 머리 세 칸(%H·%ae·%an)과 경로는 자리로만 읽는다:
    NUL은 commit 머리에도 경로에도 들어갈 수 없으므로, 이름·메일·경로에 \\x01·\\x02·줄바꿈 같은 어떤 바이트가 있어도 새 기록을 열지 못한다.
    changes면 바뀐 경로도 읽는다(-M --name-status --diff-merges=dense-combined): 보통 commit은 첫 상태 앞에 \\n이 붙고,
    merge는 머리 뒤에 빈 칸이 하나 온다(바뀐 경로가 없어도). 모양이 다르면 LogFormatError를 던진다(어림잡아 읽지 않는다)."""
    diff = ('-M', '--name-status', '--diff-merges=dense-combined') if changes else ()
    tokens = git(path, 'log', '-z', '--format=%H%x00%ae%x00%an', *diff, *revs, timeout=600, env=env).split('\0')
    if tokens.pop() != '': raise LogFormatError('git log 출력이 NUL로 끝나지 않음')
    out, i, n = [], 0, len(tokens)
    while i < n:
        if i + 2 >= n or not SHA.fullmatch(tokens[i]): raise LogFormatError(f'git log 출력의 {i}번째 칸에 commit 머리가 없음')
        sha, mail, name, entries, i = tokens[i], tokens[i + 1].lower(), tokens[i + 2], [], i + 3
        if changes and i < n:
            if tokens[i] == '': i += 1                                 # merge: 합친 diff 앞의 빈 칸
            elif tokens[i][:1] == '\n': tokens[i] = tokens[i][1:]      # 보통 commit: 첫 상태 앞의 \n
            while i < n and STATUS.fullmatch(tokens[i]):
                k = 2 if re.fullmatch(r'[RC][0-9]+', tokens[i]) else 1  # 이름 바꾸기·복사는 옛 경로와 새 경로
                if i + k >= n or not all(tokens[i + 1:i + 1 + k]): raise LogFormatError(f'git log 출력의 {i}번째 상태 뒤에 경로가 없음')
                entries.append((tokens[i], tokens[i + 1:i + 1 + k]))
                i += 1 + k
        out.append((sha, mail, name, entries))
    return out


def kind_of(mail, name, emails, names):
    """작성자 구분: 메일(소문자)이 본인 메일이면 own, 이름만 같으면 name_only(추정), 아니면 other."""
    return 'own' if mail in emails else 'name_only' if name in names else 'other'


def own_commits(path, revs, api_shas, emails, names):
    """main·develop에서 닿는 commit을 SHA 기준으로 한 번만 세고, 본인 여부를 근거별로 나눈다(작성자는 log_commits로 읽은 commit 원본)."""
    rows = log_commits(path, revs)
    kinds = {}
    for sha, mail, name, _ in rows:
        if sha in api_shas: kinds[sha] = 'api'
        elif mail in emails: kinds[sha] = 'email'
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


def history(path, sha, emails, names, env=None):
    """평가 commit까지의 commit이 바꾼 경로를 git log 한 번으로 본다. blame 없이도 결과를 아는 파일을 가리기 위해서다.
    돌려주는 것: 경로별 바뀐 횟수, 한 번 추가되고 끝난 경로의 작성자 구분(own·name_only·other),
    본인·이름 일치 commit이 닿았을 수 있는 경로(이름 바꾸기를 따라가고, 같은 commit의 삭제+추가도 이름 바꾸기로 넉넉히 본다).
    작성자는 commit에 적힌 값(%ae·%an)이다: .mailmap을 적용하지 않으므로 레포에 심은 .mailmap이 팀원 commit을 본인 commit으로 바꾸지 못한다.
    출력은 NUL 구분으로 자리대로 읽는다(log_commits): 이름·메일·경로 안의 바이트가 새 기록을 열지 못한다.
    merge commit은 어느 부모와도 다른 경로(충돌 해결)만 나온다. env(None이면 ENV)는 git log에 넘긴다."""
    return changed_paths(log_commits(path, [sha], env, changes=True), emails, names)


def changed_paths(commits, emails, names):
    """log_commits(changes=True)가 읽은 commit들로 history의 결과(바뀐 횟수, 한 번 추가된 경로의 작성자, 본인이 닿은 경로)를 만든다."""
    touches, added, reach, moves = {}, {}, set(), []
    for _, mail, name, entries in commits:
        kind, gone, new = kind_of(mail, name, emails, names), [], []
        for status, ps in entries:
            p = ps[-1]
            if len(ps) == 2: moves.append(([ps[0]], [p]))  # 이름 바꾸기·복사: 옛 경로 → 새 경로
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


def scan_blobs(path, entries, chunk=500, env=None):
    """entries [(경로, blob)]의 파일마다 줄 수(blame이 세는 방식: 마지막 줄에 줄바꿈이 없어도 한 줄)와 생성 파일 여부(paths.generated)를 구한다.
    blob은 git cat-file 묶음으로 한 번만 읽고, 내용이 같은 파일은 읽은 것을 함께 쓴다. 돌려주는 것: {경로: (줄 수, 생성 파일인가)}.
    읽지 못한 blob(cat-file이 missing으로 답함. 부분 clone에서 내려받지 못한 경우)의 경로는 넣지 않는다: 건너뛴 파일과 같다.
    env(None이면 ENV)는 git cat-file에 넘긴다."""
    by_blob, scanned = {}, {}
    for p, blob in entries: by_blob.setdefault(blob, []).append(p)
    blobs = sorted(by_blob)
    for k in range(0, len(blobs), chunk):
        out = subprocess.run(['git', '-C', str(path), 'cat-file', '--batch'], input=('\n'.join(blobs[k:k + chunk]) + '\n').encode(),
                             capture_output=True, env=ENV if env is None else env, timeout=600, check=True).stdout
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


def blame(path, sha, emails, names, env=None):
    """평가 commit에서 줄마다 마지막 작성자를 보고, 본인 줄을 증거 단위 {sha, path, lines}로 묶는다.
    경로·내용 필터(paths.skipped·generated)에 걸린 파일은 어디에도 세지 않는다.
    나머지는 모든 파일을 blame한 결과와 같되, 결과가 정해진 파일은 줄 수만 센다: 본인·이름 일치 commit이 닿지 않은 파일(전부 다른 사람),
    한 번 추가되고 바뀐 적 없는 파일(전부 그 commit 작성자). 커널 소스처럼 한 번에 올린 파일 수만 개도 몇 초 안에 끝난다.
    blame이 실패하면(부분 clone이 받지 않은 옛 blob을 내려받지 못함, 시간 초과) 처음 실패한 파일로 BlameError를 던진다.
    줄마다 작성자는 blame이 준 commit의 원래 작성자다: git log -z(log_commits)를 한 번 읽어 빠른 길(history)과 함께 쓰고, 지도에 없는 commit은 other다.
    porcelain의 author-mail·author는 쓰지 않는다: .mailmap을 따르는데 blame에는 끄는 옵션이 없고 작업 트리의 .mailmap은 설정으로 끌 수 없다(git 2.55 실측).
    그래도 분석은 checkout 없는 clone(sync)에서 mailmap 설정을 끈 gitenv 환경으로 한다(겹친 방어).
    env(None이면 ENV)는 이 함수가 돌리는 모든 git(ls-tree·log·cat-file·blame)에 넘긴다: log와 blame이 같은 graft(replace ref)를 본다.
    gitenv.env(...)로 만든 환경이어야 한다."""
    env = ENV if env is None else env
    count, units = dict(own=0, name_only=0, other=0, files=0), []
    entries = []
    # ls-tree -l은 GIT_NO_LAZY_FETCH로 돈다: 부분 clone이 받지 않은 blob을 크기 보느라 내려받지 않는다(크기 칸이 BAD)
    for entry in git(path, 'ls-tree', '-r', '-l', '-z', sha, env={**env, 'GIT_NO_LAZY_FETCH': '1'}).split('\0'):
        if not entry: continue
        meta, p = entry.split('\t', 1)
        _, kind, blob, size = meta.split()
        # 부분 clone이 받지 않은 blob은 크기가 BAD로 나온다: 숫자와 상관없이 건너뛴다(512KiB 이상이라 paths.skipped와 같은 파일)
        if kind == 'blob' and size != 'BAD' and not skipped(p, int(size)): entries.append((p, blob))
    commits = log_commits(path, [sha], env, changes=True)  # 한 번 읽어 빠른 길과 blame 줄의 작성자에 함께 쓴다
    touches, added, reach = changed_paths(commits, emails, names)
    author = {c: kind_of(mail, name, emails, names) for c, mail, name, _ in commits}  # commit → 원래 작성자의 구분
    known = lambda p: p not in reach or (touches.get(p) == 1 and p in added)
    scanned = scan_blobs(path, entries, env=env)  # 후보 blob을 한 번씩만 읽는다: 줄 수(빠른 길 파일)와 생성 파일 여부(모든 파일)
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
                                  capture_output=True, env=env, timeout=120, check=True).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:  # 파일 하나를 조용히 빼면 덜 센 결과가 성공처럼 남는다
            raise BlameError(p) from e
        count['files'] += 1
        mine, line, commit = [], None, None
        for row in out.split(b'\n'):
            if row.startswith(b'\t'):  # 줄 내용: 바로 앞 머리 줄의 commit이 쓴 줄
                who = author.get(commit, 'other')
                count[who] += 1
                if who == 'own': mine.append(line)
            elif re.match(rb'[0-9a-f]{40,64} \d+ \d+', row):  # 머리 줄: <commit> <원래 줄> <지금 줄> [<묶음 줄 수>]
                fields = row.split()
                commit, line = fields[0].decode(), int(fields[2])
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
    issues = [i for i in api.pages(f'/repos/{full}/issues', {'state': 'all', 'per_page': 100}, max_pages=3, empty=(409, 410))  # 410 = 이슈를 끈 레포: 이슈 0
              if 'pull_request' not in i]
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
        found, failed = {}, {}  # failed: 검색으로 찾았지만 조회하지 못한 레포 → 이유
        for kind in ('owner', 'member'):
            for r in api.pages(f'/users/{login}/repos', {'type': kind, 'per_page': 100}, max_pages=None):
                if not r['private']: found.setdefault(r['full_name'], (r, kind))
        search = lambda path, q: api.pages(path, {'q': q, 'per_page': 100}, max_pages=SEARCH_PAGES, key='items')
        commits = list(search('/search/commits', f'author:{login} is:public'))
        prs = list(search('/search/issues', f'author:{login} type:pr is:public'))
        mine = {i['repository']['full_name'] for i in commits}  # 본인 commit이 검색된 레포(검색은 기본 브랜치만 본다: 순서에만 쓴다)
        searched = mine | {i['repository_url'].split('/repos/')[1] for i in prs}
        for full in sorted(searched - set(found)):
            try: r, _, _ = api.get(f'/repos/{full}', ok=(200, 404))
            except StopCheck as e: failed[full] = f'API 실패: {e}'; continue  # 레포 하나의 조회 실패(5xx·403·451·한도 소진)는 그 레포만 미확인
            if not r or r['private']: continue
            if full in mine: mine.add(r['full_name'])  # 이름을 바꾸거나 옮긴 레포는 옛 이름으로 검색되고 새 이름으로 온다
            found.setdefault(r['full_name'], (r, 'search'))  # 실제 이름으로 한 번만 넣는다(같은 레포를 두 번 처리하면 저장이 깨진다)
        repos = sorted(found.values(), key=lambda x: x[0]['full_name'] not in mine)  # 상한 없음. 안정 정렬이라 나머지 순서는 그대로
        res['external_pr_repos'] = sorted({full for full, (_, kind) in found.items() if kind != 'owner'} | set(failed))

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
        for full, error in failed.items():  # 조회하지 못한 레포: 정보를 모르니 이유만 남긴다(fork는 알 수 없어 False로 둔다)
            res['repos'].append(dict(full=full, fork=False, default_branch=None, size_kb=None, source='search', error=error))

        # 2단계: 본인 commit·본인 줄(로컬) → 실행·활용 기록(API)
        for row, path, api_shas in work:
            try: local, units = analyze_repo(path, row['heads'], api_shas, emails, names)
            except BlameError as e: row['error'] = f'blame 실패: {e.path}'; continue  # 파일 하나가 빠진 결과로 판정하지 않는다(다시 수집할 때까지 제외)
            except ValueError as e: row['error'] = f'git 출력 해석 실패: {e}'; continue  # LogFormatError·UnicodeDecodeError도 ValueError다: 어림잡아 세지 않는다
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
