"""lv-stat 스테이징: GitHub 계정 하나를 분석한다(레포 찾기 → 레포 받기 → 색인 → 규칙 적용 → 계산). 2026-11-27 첫 판.

analyze(job, work_root, deadline, progress)가 CONTRACT.md의 profile을 돌려준다. 작업자(worker.py)가 부른다.
- 2단계 규칙 코드(s2/)는 고치지 않고 감싼다. s2 모듈은 불러올 때 작업 폴더(LV_S2_HOME)를 정하므로, 단계마다 새 프로세스
  (python3 -I -B, LV_S2_HOME = 요청 작업 폴더의 절대 경로)로 돌린다. 계산(calc)도 자식 프로세스에서 한다(요청끼리 섞이지 않게).
  -B: -I는 PYTHONDONTWRITEBYTECODE를 읽지 않으므로, 코드 폴더에 컴파일 파일을 쓰지 않게 따로 준다.
- 레포 찾기(GitHub API, GET만): 본인 소유 공개·포크 아닌 레포 중 기본 브랜치에 내 커밋이 있는 것 + 커밋 검색으로 찾은 남의
  공개·포크 아닌 레포. 최근 push 순으로 자른다. 커밋 검색은 best-effort(한도·오류면 notes에 남기고 계속).
- 받기: git clone --no-checkout. 1MB 넘는 파일 내용은 받지 않고, 큰 레포는 내용 없이 받은 뒤 .git/lv-partial을 만든다(s2_index가
  내 경로만 받는다). 토큰 없이 받는다(s2lib.GENV). 토큰은 GitHub API(이 프로세스의 ghapi, 색인 단계)에만 쓴다.
  받은 레포의 코드는 실행하지 않는다(git 명령만).
- 색인 결과는 레포 파일마다 읽는다(s2_index는 레포마다 실패를 error로 남기고 0으로 끝난다): 호출 한도면 요청 실패(UserError),
  그 밖의 실패는 repos.failed와 notes. 시간을 넘기면 색인한 레포만으로 계속한다.
- LLM 보충은 끈다(s2_final). 추출기·마무리가 실패하면 notes에 남기고 계속한다. 추출기가 쓰다 만 vars 파일은 마무리 전에 지운다.
- 모든 단계는 마감(deadline) 안에 끝난다(시간 계획은 CLONE_SHARE·INDEX_SHARE·FINISH_S 설명).
- 작업 폴더 <work_root>/<요청 id>는 끝나면(실패해도) 지운다.
"""
import ast
import datetime
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

S2DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 's2')
sys.path.insert(0, S2DIR)
import ghapi as G  # noqa: E402

METHOD = 'lv-stat-s2-20261127'
LABELS = ['2단계 규칙', 'LLM 보충 끔', '제안 기준', '본인 확인 안 됨']
EXTRACTORS = ['cat_prog_deploy', 'cat_backend_a', 'cat_backend_b', 'cat_db', 'cat_de', 'cat_fe', 'cat_ai']
# out/<pid>/vars-<키>.json → 그 파일을 쓰는 추출기(s2_final.MODULE_OF와 같은 표. 시험이 같은지 본다)
VARS_OF = {'prog': 'cat_prog_deploy', 'deploy': 'cat_prog_deploy', 'backend_a': 'cat_backend_a', 'backend_b': 'cat_backend_b',
           'de': 'cat_de', 'db': 'cat_db', 'fe': 'cat_fe', 'ai': 'cat_ai'}
CODES = ('L', 'O', 'B', 'E', 'D', 'F', 'A')    # CONTRACT categories
PID = 'P01'                                    # people.json의 사람 번호(cat_ai는 ^P\d\d$만 받는다)

# 「Claude 임시값」(CLAUDE.md '스테이징 LV 서비스': 레포 수·분석 시간 상한)
MAX_REPOS = 40             # 분석할 레포 수
OWN_PAGES = 3              # 본인 소유 레포 목록 쪽 수(쪽마다 100개)
SEARCH_PAGES = 3           # 커밋 검색 쪽 수(쪽마다 100개)
BIG_KB = 400 * 1024        # GitHub size(KB)가 이보다 크면 큰 레포(400MB 넘음): --filter=blob:none + .git/lv-partial
CLONE_MIN_S = 60           # 받기 몫이 이만큼(초) 남지 않으면 더 받지 않는다
# 시간 계획: 모든 단계가 마감(deadline) 안에 끝난다. 끝의 마무리(s2_final)·계산(calc) 몫(각 FINISH_S)을 먼저 떼고, 시작할 때
# 남은 나머지(work = deadline − 2×FINISH_S − 시작 시각)를 앞 단계에 나눈다(받기가 길어져도 받은 레포는 분석한다).
# 20분이면 받기 8분·색인 12.8분째까지·추출기 16분째까지·마무리 18분째까지·계산 20분까지.
CLONE_SHARE = 0.5          # 「Claude 임시값」 받기는 work의 절반까지
INDEX_SHARE = 0.8          # 「Claude 임시값」 색인은 work의 8할까지. 추출기는 work 끝(deadline − 2×FINISH_S)까지
FINISH_S = 120             # 「Claude 임시값」 마무리는 deadline − FINISH_S까지, 계산은 deadline까지, 단계마다 이만큼(초)까지

MSG_NO_USER = 'GitHub 계정을 찾을 수 없습니다. 주소를 확인해 주세요.'
MSG_ORG = '개인 GitHub 계정 주소를 넣어 주세요(조직 계정은 분석하지 않습니다).'
MSG_NO_REPOS = '공개 레포에서 이 계정의 커밋을 찾지 못했습니다.'
MSG_NO_CLONE = '레포를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.'
MSG_NO_INDEX = '레포를 색인하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'
NOTE_SEARCH = '커밋 검색을 하지 못해 남의 레포를 다 찾지 못함'

TIMED_OUT = 'timeout'                          # run_step이 시간을 넘겼을 때 돌려주는 글
API_STEPS = ('s2_index.py',)                   # GitHub API를 부르는 단계. 이 단계만 토큰을 받는다
GITHUB_ENV = ('LV_GITHUB_API', 'LV_GITHUB_OFFLINE', 'LV_GITHUB_TOKEN')   # ghapi가 읽는 환경 변수
POLL_S = 1.0                                   # 자식 프로세스를 기다리며 진행을 보는 간격(초)
TAIL = 2000                                    # 로그에 남기는 자식 출력의 끝 글자 수
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
CALC = 'import json, sys; sys.path.insert(0, sys.argv[1]); import calc; print(json.dumps(calc.calc_person(sys.argv[2])))'

log = logging.getLogger(__name__)


class UserError(RuntimeError):
    """사용자에게 그대로 보이는 실패(짧은 한국어)."""


def now_iso():
    """지금(UTC)을 ISO 8601로. 예: '2026-11-28T01:02:03Z'"""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _s2lib():
    """s2lib(GENV·PARTIAL_MARK)를 처음 쓸 때 불러온다. s2lib는 불러올 때 작업 폴더(LV_S2_HOME, 없으면 코드 폴더)를 정하고 그 아래
    빈 HOME 폴더를 만든다. 이 프로세스는 git 환경만 쓰고 s2 단계는 모두 자식 프로세스로 돌리므로, analyze를 불러오기만 해서는
    아무것도 생기지 않게 미룬다."""
    import s2lib
    return s2lib


# ---------------- 레포 찾기
def _repo(info, owned):
    size = info.get('size')
    return dict(full_name=info['full_name'], default_branch=info.get('default_branch') or 'main',
                size=size if isinstance(size, int) else 0, pushed_at=info.get('pushed_at'), owned=owned)


def _repo_path(full_name):
    """'owner/name' → API 경로 조각(이름마다 인코딩)."""
    return '/'.join(G.q(part) for part in full_name.split('/', 1))


def _searched(login, names, notes):
    """커밋 검색(작성자 = login)으로 찾은 레포 중 names(이미 찾은 레포, 소문자)에 없는 공개·포크 아닌 레포. 정보는 repos/{full}로
    받는다. best-effort: 호출 한도(RateLimited)나 그 밖의 GitHub 오류(2차 한도 403 + Retry-After 등)면 notes에 남기고 찾은 만큼."""
    found, me = [], login.lower()
    try:
        items = G.get_all(f'search/commits?q=author:{G.q(login)}&sort=committer-date&order=desc&per_page=100',
                          max_pages=SEARCH_PAGES)
        for item in items:
            repo = item.get('repository') or {}
            full = repo.get('full_name')
            if not full or full.lower() in names or repo.get('fork') or repo.get('private'):
                continue
            names.add(full.lower())
            info = G.get(f'repos/{_repo_path(full)}')
            if info and not info.get('fork') and not info.get('private'):
                found.append(_repo(info, owned=(info.get('owner') or {}).get('login', '').lower() == me))
    except (G.RateLimited, G.GitHubError):
        notes.append(NOTE_SEARCH)
    return found


def discover(login, notes):
    """계정의 분석할 레포 -> (정식 login, [{full_name, default_branch, size(KB), pushed_at, owned}]).
    pushed_at 최근 순으로 MAX_REPOS개까지. 본인 소유 레포는 기본 브랜치에 내 커밋이 있는 것만(차례대로 물어 자른 뒤로는 묻지 않음).
    계정이 없거나 조직이면 UserError. 호출 한도(RateLimited)는 그대로 올린다(커밋 검색만 best-effort)."""
    user = G.get(f'users/{G.q(login)}')
    if not isinstance(user, dict) or not user.get('login'):
        raise UserError(MSG_NO_USER)
    if user.get('type') != 'User':
        raise UserError(MSG_ORG)
    login = user['login']
    owned, forks = [], 0
    for r in G.get_all(f'users/{G.q(login)}/repos?type=owner&sort=pushed&per_page=100', max_pages=OWN_PAGES):
        if not r.get('full_name') or r.get('private'):
            continue
        if r.get('fork'):
            forks += 1
        else:
            owned.append(_repo(r, owned=True))
    if forks:
        notes.append(f'포크 레포 {forks}개는 뺌')
    found = owned + _searched(login, {r['full_name'].lower() for r in owned}, notes)
    found.sort(key=lambda r: r['pushed_at'] or '', reverse=True)
    repos = []
    for r in found:
        if len(repos) == MAX_REPOS:
            notes.append(f'레포가 많아 최근 {MAX_REPOS}개만 봄')
            break
        if r['owned'] and not G.get(f"repos/{_repo_path(r['full_name'])}/commits?author={G.q(login)}&per_page=1"
                                    f"&sha={G.q(r['default_branch'])}"):
            continue                         # 기본 브랜치에 내 커밋이 없음(빈 레포는 409 → 없음)
        repos.append(r)
    return login, repos


# ---------------- 자식 프로세스
def _spawn(argv, env, timeout, poll=None):
    """argv를 새 세션(프로세스 묶음)의 자식으로 돌린다. timeout초를 넘기면 묶음 전체를 끝낸다(os.killpg: git 같은 손주까지).
    출력은 임시 파일로 받는다(파이프가 차서 멈추지 않게). 기다리는 동안 POLL_S초마다 poll()을 부른다.
    -> (종료 코드(시간을 넘겼으면 None), stdout 글자, stderr 글자)"""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env, start_new_session=True)
        end = time.monotonic() + timeout
        rc = None
        try:
            while True:
                try:
                    rc = p.wait(timeout=max(0.0, min(POLL_S, end - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= end:
                        break
                    if poll:
                        poll()
        finally:
            if rc is None:                   # 시간을 넘김(또는 기다리다 예외). 아직 거두지 않아 묶음 번호(= pid)가 그대로다
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait()
        out.seek(0)
        err.seek(0)
        return rc, out.read().decode('utf-8', 'replace'), err.read().decode('utf-8', 'replace')


def _child_env(home, api):
    """s2 자식 프로세스의 환경: s2lib.GENV(토큰 없음, lazy fetch 막음, 빈 HOME) + LV_S2_HOME. ghapi 값(LV_GITHUB_*)은 빼고,
    GitHub API를 부르는 단계만 지금 값(토큰 포함)을 넣는다. 추출기에는 git을 GENV 없이 부르는 곳(cat_backend_a_oc)이 있어
    이 환경이 곧 그 git의 환경이다."""
    env = {k: v for k, v in _s2lib().GENV.items() if k not in GITHUB_ENV}
    env['LV_S2_HOME'] = home
    if api:
        env.update((k, os.environ[k]) for k in GITHUB_ENV if k in os.environ)
    return env


def run_step(script, home, timeout, poll=None):
    """s2 단계 하나(python3 -I -B <s2>/<script> P01)를 새 세션의 자식 프로세스로 돌린다. LV_S2_HOME은 home의 절대 경로다.
    GitHub API를 부르는 단계(s2_index)만 토큰을 받는다. timeout초를 넘기면 프로세스 묶음 전체를 끝낸다.
    -> (0으로 끝났으면 참, 시간을 넘겼으면 TIMED_OUT, 아니면 출력의 끝 부분)"""
    home = os.path.abspath(home)
    rc, out, err = _spawn([sys.executable, '-I', '-B', os.path.join(S2DIR, script), PID],
                          _child_env(home, os.path.basename(script) in API_STEPS), timeout, poll)
    if rc is None:
        return False, TIMED_OUT
    return rc == 0, (out + err)[-TAIL:]


# ---------------- 받기
def clone(full_name, dest, big, timeout, run=None):
    """https://github.com/<full_name>.git을 dest에 받는다(--no-checkout, 토큰 없이 s2lib.GENV). 1MB 넘는 파일 내용은 받지 않고,
    큰 레포(big)는 내용 없이 받은 뒤 .git/lv-partial을 만든다. timeout초를 넘기면 그만둔다. run은 시험용 자리
    (기본은 새 세션 자식 프로세스, 시간을 넘기면 묶음 전체를 끝냄). -> 받았으면 참(못 받으면 dest를 지운다)"""
    s2 = _s2lib()
    argv = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.file.allow=never', 'clone', '--no-checkout', '--no-tags',
            '--quiet', '--filter=blob:none' if big else '--filter=blob:limit=1m', f'https://github.com/{full_name}.git', dest]
    rc, _, err = (run or _spawn)(argv, s2.GENV, timeout)
    if rc != 0:
        log.warning('레포 받기 실패 %s: %s', full_name, '시간 초과' if rc is None else err.strip()[-300:])
        shutil.rmtree(dest, ignore_errors=True)
        return False
    if big:
        with open(os.path.join(dest, '.git', s2.PARTIAL_MARK), 'w'):
            pass
    return True


def _branches(d):
    """받은 레포에 develop·dev 브랜치가 있는지(clone이 받은 refs/remotes/origin/*로 본다. API는 부르지 않는다)."""
    want = ('develop', 'dev')
    rc, out, _ = _spawn(['git', '-C', d, 'for-each-ref', '--format=%(refname)', *('refs/remotes/origin/' + b for b in want)],
                        _s2lib().GENV, 60)
    refs = set(out.split()) if rc == 0 else set()
    return {'has_' + b: 'refs/remotes/origin/' + b in refs for b in want}


def _clone_all(repos, home, clone_end, progress, clone_fn, notes):
    """레포를 차례로 받는다. 받기 몫(clone_end까지)이 CLONE_MIN_S초 아래로 남으면 그만둔다.
    -> (people.json의 레포 칸 목록, 받지 못한 수). 하나도 못 받으면 UserError."""
    os.makedirs(os.path.join(home, 'repos'))
    entries, failed, total = [], 0, len(repos)
    progress('레포 받기', 0, total)
    for i, r in enumerate(repos):
        left = clone_end - time.time()
        if left < CLONE_MIN_S:
            notes.append(f'시간 상한에 닿아 레포 {total - i}개는 받지 못함')
            break
        # 키는 파일·폴더 이름으로 쓴다: 차례 번호(겹치지 않음) + 영문·숫자·._-만 남긴 이름
        key = '%02d-%s' % (i + 1, re.sub(r'[^A-Za-z0-9._-]', '_', r['full_name'].replace('/', '__'))[:80])
        dest = os.path.join(home, 'repos', key)
        big = r['size'] > BIG_KB
        if clone_fn(r['full_name'], dest, big, left):
            # PR 목록은 본인 소유·포크 아님·400MB 이하 레포만 받는다(2단계 범위. s2_index는 레포의 PR을 끝까지 받는다)
            entries.append(dict(key=key, full_name=r['full_name'], dir=dest, default_branch=r['default_branch'],
                                **_branches(dest), prs=r['owned'] and not big, evidence=False))
        else:
            failed += 1
        progress('레포 받기', i + 1, total)
    if failed:
        notes.append(f'레포 {failed}개는 받지 못함')
    if not entries:
        raise UserError(MSG_NO_CLONE)
    return entries, failed


# ---------------- 색인
def _write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def _load_json(path):
    """JSON 파일 → 값. 없거나 깨졌으면 None."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _rate_limit_message(err):
    """색인 레코드의 error(repr(RateLimited(메시지))[:300]) → 그 메시지('GitHub 호출 한도에 걸렸습니다(N분 뒤 다시 시도)')."""
    try:
        msg = ast.literal_eval(err[len('RateLimited('):-1])
    except (ValueError, SyntaxError):
        msg = None
    return msg if isinstance(msg, str) and msg else err


def _index(home, login, entries, index_end, progress, notes):
    """색인 단계(s2_index). 레포 파일마다 결과를 읽는다. 시간을 넘기거나 실패하면 색인 파일이 있는 레포만으로 person.json을
    쓴다(s2_index와 같은 칸). -> (색인한 레포 수, 색인하지 못한 레포 수(시간 상한으로 못 한 것은 빼고))"""
    idx = os.path.join(home, 'index', PID)
    total, shown = len(entries), [0]
    progress('색인', 0, total)

    def poll():
        try:
            n = sum(1 for f in os.listdir(idx) if f.endswith('.json') and f != 'person.json')
        except OSError:
            return
        if n != shown[0]:
            shown[0] = n
            progress('색인', n, total)

    t = time.time()
    ok, msg = run_step('s2_index.py', home, index_end - time.time(), poll=poll)
    timed_out = msg == TIMED_OUT
    if not ok:
        log.warning('색인 %s: %s', '시간 상한' if timed_out else '실패', msg)
    keys, missing, failed, analyzed, unfetched, unblamed = [], 0, 0, 0, 0, 0
    for e in entries:
        path = os.path.join(idx, e['key'] + '.json')
        rec = _load_json(path)
        if not isinstance(rec, dict):        # 색인하지 못함(끝낸 순간에 쓰던 파일은 반쯤 쓴 채다). repo_keys에 넣지 않으므로
            missing += 1                     # 추출기는 읽지 않는다(s2lib.Person은 repo_keys의 파일만 읽음)
            continue
        keys.append(e['key'])
        err = rec.get('error')
        if err:
            if str(err).startswith('RateLimited('):
                raise UserError(_rate_limit_message(str(err)))
            failed += 1
            continue
        analyzed += 1
        part = rec.get('partial')            # 큰 레포(.git/lv-partial)만 있다
        if isinstance(part, dict):
            unfetched += part.get('fetched') is False
            count = (part.get('blame_failed') or {}).get('count')
            unblamed += count if isinstance(count, int) else 0
    if missing and timed_out:
        notes.append(f'시간 상한에 닿아 레포 {missing}개는 색인하지 못함')
    else:
        failed += missing
    if failed:
        notes.append(f'레포 {failed}개는 색인하지 못함')
    if unfetched:
        notes.append(f'큰 레포 {unfetched}개는 파일을 받지 못함')
    if unblamed:
        notes.append(f'큰 레포에서 내 줄을 세지 못한 파일 {unblamed}개')
    progress('색인', len(keys), total)
    if not analyzed:
        raise UserError(MSG_NO_INDEX)
    if not ok or not isinstance(_load_json(os.path.join(idx, 'person.json')), dict):
        _write_json(os.path.join(idx, 'person.json'), dict(pid=PID, login=login, role=None, level=None, repo_keys=keys,
                                                           index_s=round(time.time() - t, 1)))
    return analyzed, failed


# ---------------- 규칙 적용·계산
def _rules(home, rules_end, progress, notes):
    """추출기 7개를 차례로 돌린다(각자 rules_end까지). 오류로 실패한 추출기는 notes에 이름을 남기고 다음으로 간다.
    시간 상한에 닿아 끝낸 추출기와 시작하지 못한 추출기는 notes 한 줄로 센다.
    -> notes가 이미 다룬 추출기 이름(실패·시간 상한)"""
    total = len(EXTRACTORS)
    progress('규칙 적용', 0, total)
    covered, cut = set(), 0
    for i, name in enumerate(EXTRACTORS, 1):
        left = rules_end - time.time()
        if left <= 0:
            cut += 1                         # 시작하지 못함
        else:
            ok, msg = run_step(name + '.py', home, left)
            if not ok:
                covered.add(name)
                if msg == TIMED_OUT:
                    cut += 1
                else:
                    notes.append(f'규칙 적용 실패: {name}')
                log.warning('%s %s: %s', name, '시간 상한' if msg == TIMED_OUT else '실패', msg)
        progress('규칙 적용', i, total)
    if cut:
        notes.append(f'시간 상한에 닿아 규칙 {cut}개는 적용하지 못함')
    return covered


def _drop_broken_vars(home, covered, notes):
    """반쯤 쓴 vars-*.json(추출기가 쓰다가 끝남·멈춤)을 지운다. s2_final은 vars 파일을 모두 읽은 뒤 마무리하므로, 깨진 파일이
    하나라도 있으면 모든 카테고리를 마무리하지 못한다. 그 추출기를 notes가 아직 다루지 않았으면 '규칙 적용 실패: <이름>'을 남긴다."""
    out = os.path.join(home, 'out', PID)
    for name in sorted(os.listdir(out)) if os.path.isdir(out) else []:
        m = re.fullmatch(r'vars-(\w+)\.json', name)
        if not m or isinstance(_load_json(os.path.join(out, name)), dict):
            continue
        os.remove(os.path.join(out, name))
        extractor = VARS_OF.get(m.group(1), m.group(1))
        log.warning('반쯤 쓴 규칙 결과를 지움: %s', name)
        if extractor not in covered:
            covered.add(extractor)
            notes.append(f'규칙 적용 실패: {extractor}')


def _is_level(v):
    return type(v) in (int, float) and 0 <= v <= 5


def _categories(res):
    """calc_person 결과 → CONTRACT categories(이름·lv·unknown, L은 languages·best, B는 note). 모양이 다르면 ValueError
    (웹은 모양이 다른 프로필을 읽지 않으므로 여기서 실패로 드러낸다)."""
    out = {}
    for code in CODES:
        c = res.get(code) if isinstance(res, dict) else None
        if not (isinstance(c, dict) and isinstance(c.get('name'), str) and (c.get('lv') is None or _is_level(c['lv']))
                and type(c.get('unknown')) is int and c['unknown'] >= 0):
            raise ValueError(f'계산 결과 모양이 다름: {code}')
        box = dict(name=c['name'], lv=c['lv'], unknown=c['unknown'])
        if code == 'L':
            langs, best = c.get('languages'), c.get('best')
            if not (isinstance(langs, dict) and all(isinstance(k, str) and _is_level(v) for k, v in langs.items())
                    and (best in langs if langs else best is None)):
                raise ValueError('계산 결과 모양이 다름: L')
            box.update(languages=langs, best=best)
        elif code == 'B' and isinstance(c.get('note'), str):
            box['note'] = c['note']
        out[code] = box
    return out


def _finish(home, deadline, notes):
    """LLM 없는 마무리(s2_final, deadline − FINISH_S까지)와 계산(calc, 자식 프로세스, deadline까지) → categories.
    단계마다 FINISH_S초까지다. 마무리하지 못한 카테고리는 notes에 남긴다."""
    ok, msg = run_step('s2_final.py', home, min(FINISH_S, deadline - FINISH_S - time.time()))
    if not ok:
        notes.append('규칙 마무리 실패')
        log.warning('s2_final 실패: %s', msg)
    out = os.path.join(home, 'out', PID)
    for name in sorted(os.listdir(out)) if os.path.isdir(out) else []:
        m = re.fullmatch(r'final-(\w+)\.json', name)
        if not m:
            continue
        rec = _load_json(os.path.join(out, name))
        if not isinstance(rec, dict):        # 마무리가 쓰다 만 파일(계산이 읽다 멈추지 않게 지운다)
            os.remove(os.path.join(out, name))
            notes.append(f'규칙 마무리 실패: {m.group(1)}')
        elif rec.get('finalize_error'):
            notes.append(f'규칙 마무리 실패: {m.group(1)}')
    rc, stdout, err = _spawn([sys.executable, '-I', '-B', '-c', CALC, S2DIR, PID], _child_env(home, False),
                             min(FINISH_S, deadline - time.time()))
    if rc != 0:
        raise RuntimeError(f'계산 실패({"시간 초과" if rc is None else rc}): {err.strip()[-300:]}')
    return _categories(json.loads(stdout))


# ---------------- 계정 하나
def analyze(job, work_root, deadline, progress, clone_fn=clone):
    """요청 하나(job: id·namespace·subjectId·login)를 분석해 CONTRACT.md의 profile을 돌려준다. deadline은 절대 시각(epoch 초).
    progress(단계 이름, done, total)로 진행을 알린다. 사용자에게 보일 실패는 UserError(GitHub 호출 한도는 ghapi.RateLimited일 수도
    있다). 작업 폴더 <work_root>/<job id>는 끝나면(실패해도) 지운다."""
    job_id = str(job.get('id') or '')
    if not UUID.fullmatch(job_id):
        raise ValueError('요청 id가 uuid가 아님')      # 작업 폴더 이름으로 쓴다
    t0 = time.time()
    work = deadline - 2 * FINISH_S - t0      # 규칙 적용까지 쓸 시간(마무리·계산 몫을 뗌. 머리의 시간 계획)
    home = os.path.join(os.path.abspath(work_root), job_id)
    shutil.rmtree(home, ignore_errors=True)
    os.makedirs(home, mode=0o700)
    try:
        notes = []
        progress('레포 찾기', None, None)
        login, repos = discover(job['login'], notes)
        if not repos:
            raise UserError(MSG_NO_REPOS)
        entries, clone_failed = _clone_all(repos, home, t0 + work * CLONE_SHARE, progress, clone_fn, notes)
        _write_json(os.path.join(home, 'people.json'), [dict(pid=PID, login=login, role=None, level=None, repos=entries)])
        analyzed, index_failed = _index(home, login, entries, t0 + work * INDEX_SHARE, progress, notes)
        covered = _rules(home, deadline - 2 * FINISH_S, progress, notes)
        _drop_broken_vars(home, covered, notes)
        progress('계산', None, None)
        categories = _finish(home, deadline, notes)
        return dict(schema='lv-stat-profile/1', method=METHOD, labels=list(LABELS), namespace=job['namespace'],
                    subjectId=job['subjectId'], login=login, jobId=job_id, analyzedAt=now_iso(),
                    repos=dict(found=len(repos), analyzed=analyzed, failed=clone_failed + index_failed, notes=notes),
                    categories=categories)
    finally:
        shutil.rmtree(home, ignore_errors=True)
