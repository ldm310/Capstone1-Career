"""lv-stat 스테이징: 분석 작업자. 웹이 만든 요청 파일(jobs/<id>.json)을 하나씩 집어 analyze로 분석하고 결과를 쓴다. 2026-11-27 첫 판.

python3 -I -u worker.py --data-dir <CAREER_DATA_DIR>/lv-stat [--once] [--max-minutes 20] [--poll 5] [--self-check]
- 파일 형식은 CONTRACT.md. 요청은 queued → running(stage·progress·startedAt) → done(profileKey·finishedAt) | failed(error).
  error는 실패에만 쓴다(null로 쓰지 않음). 모든 쓰기는 같은 폴더의 임시 파일에 쓴 뒤 os.replace로 바꾼다.
- 성공하면 프로필(profiles/<profileKey>.json)을 먼저 쓰고, 그다음에 요청을 done으로 바꾼다. 웹은 요청이 done이면 묻기를
  멈추고 프로필을 읽으므로, done인 요청이 옛 프로필이나 없는 파일을 가리키면 안 된다.
- 사용자에게 보이는 실패: UserError·GitHub 호출 한도(ghapi.RateLimited)는 그 메시지, 그 밖은 MSG_ERROR(자세한 것은 로그에만).
- 시작할 때 recover: 진행 중(running)이던 요청은 MSG_RESTART로 닫고 work를 비운다(작업자가 멈춘 사이 남은 것).
  같은 데이터 폴더에 작업자가 둘 돌면 recover가 남의 진행 중 요청을 닫으므로, 데이터 폴더의 .worker.lock을 잡은 작업자만 돈다.
- --self-check(배포 스크립트가 판을 바꾸기 전에 지금 데이터 폴더로 부른다): recover하지 않고 jobs·profiles·work를 고치지 않는다.
  Python ≥3.10, git, 데이터 폴더 쓰기(임시 파일을 만들고 지움), Linguist 자료, 서비스 폴더의 모든 .py 문법(메모리에서 compile).
  문제가 없으면 stdout에 OK 한 줄을 찍고 0으로 끝난다. git 판은 로그(stderr)에 남기고, 2.45보다 옛 판이면 경고만 한다.
- 토큰(LV_GITHUB_TOKEN)은 로그에 'token yes/no'만 남긴다. 값은 analyze가 GitHub API에만 쓴다.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 배포·systemd는 python3 -I로 부른다. -I는 PYTHONDONTWRITEBYTECODE를 읽지 않으므로, 불러오는 모듈(analyze·ghapi·s2lib)의 컴파일
# 파일(__pycache__)이 코드 폴더(배포한 판)에 생기지 않게 여기서 끈다. -I(3.11부터 -P 포함)는 스크립트 폴더를 sys.path에 넣지 않는다.
sys.dont_write_bytecode = True
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import analyze as A  # noqa: E402
from analyze import UserError, now_iso  # noqa: E402,F401  (UserError는 시험·호출하는 쪽도 쓴다)

RateLimited = A.G.RateLimited

MAX_MINUTES = 20      # 「Claude 임시값」 요청 하나의 분석 시간 상한(분). analyze의 deadline이 된다
POLL_S = 5            # 「Claude 임시값」 대기 중인 요청이 없을 때 jobs/를 다시 보는 간격(초)
MIN_PYTHON = (3, 10)
GIT_WANT = (2, 45)    # GIT_NO_LAZY_FETCH(s2lib.GENV)를 아는 첫 git 판. 그 전 판이면 경고만 한다
LINGUIST = ('languages.yml', 'vendor.yml', 'documentation.yml')   # s2/data/linguist 아래. 없거나 비면 자체 점검 실패
LOCK = '.worker.lock'
SECRET_ENV = ('LV_GITHUB_TOKEN', 'GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN',
              'ANTHROPIC_API_KEY')   # 자체 점검의 git에 넘기지 않는 값(s2lib.SECRET_ENV와 같음)

MSG_RESTART = '작업자가 다시 시작되어 중단됐습니다. 다시 요청해 주세요.'
MSG_ERROR = '분석 중 오류가 났습니다. 잠시 뒤 다시 시도해 주세요.'
MSG_BAD_JOB = '요청 형식이 맞지 않습니다. 다시 요청해 주세요.'
MSG_BAD_LOGIN = 'GitHub 아이디 형식이 맞지 않습니다. 주소를 확인해 주세요.'

JOB_ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}')   # uuid v4(소문자)
JOB_FILE = re.compile(JOB_ID.pattern + r'\.json')
LOGIN = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$')   # fullmatch로 쓴다(끝 줄바꿈도 막음)

log = logging.getLogger('worker')


# ---------------- 파일
def profile_key(namespace, subject_id):
    """sha256(namespace + ':' + subjectId)의 16진수 앞 32자(CONTRACT.md)."""
    return hashlib.sha256(f'{namespace}:{subject_id}'.encode('utf-8')).hexdigest()[:32]


def write_json(path, data):
    """같은 폴더의 임시 파일(.<이름>.*.tmp)에 다 쓴 뒤 os.replace로 바꾼다. 읽는 쪽은 옛 파일이나 새 파일만 본다.
    쓰다 실패하면 임시 파일을 지우고 예외를 그대로 올린다(옛 파일은 그대로)."""
    folder, name = os.path.split(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f'.{name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path):
    """JSON 파일 → 값. 없거나 깨졌으면 None."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


class Dirs:
    """데이터 폴더(<CAREER_DATA_DIR>/lv-stat)와 그 아래 jobs·profiles·work(없으면 만든다)."""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.jobs = os.path.join(self.root, 'jobs')
        self.profiles = os.path.join(self.root, 'profiles')
        self.work = os.path.join(self.root, 'work')
        for d in (self.jobs, self.profiles, self.work):
            os.makedirs(d, exist_ok=True)


# ---------------- 요청 목록
def valid_job(job):
    """요청 칸 모양: id(uuid v4)·namespace·subjectId(빈 글 아님)·login(글). login 형식은 process가 따로 본다."""
    return (isinstance(job, dict) and isinstance(job.get('id'), str) and bool(JOB_ID.fullmatch(job['id']))
            and all(isinstance(job.get(k), str) and job[k] != '' for k in ('namespace', 'subjectId'))
            and isinstance(job.get('login'), str))


def list_jobs(dirs):
    """jobs/에서 파일 이름이 '<uuid v4>.json'이고 내용이 JSON 객체인 요청 -> [(파일 이름, 요청)](이름 순).
    임시 파일·반쯤 쓴 파일·폴더·링크는 뺀다."""
    out = []
    try:
        names = sorted(os.listdir(dirs.jobs))
    except FileNotFoundError:
        return out
    for name in names:
        path = os.path.join(dirs.jobs, name)
        if not JOB_FILE.fullmatch(name) or os.path.islink(path) or not os.path.isfile(path):
            continue
        job = read_json(path)
        if isinstance(job, dict):
            out.append((name, job))
    return out


def _created(job):
    """createdAt(ISO 8601) → epoch 초. 읽지 못하면 무한대(맨 뒤). 시간대가 없으면 UTC로 본다."""
    s = job.get('createdAt')
    if not isinstance(s, str):
        return float('inf')
    try:
        t = datetime.datetime.fromisoformat(s[:-1] + '+00:00' if s.endswith(('Z', 'z')) else s)   # 3.10은 'Z'를 못 읽음
    except ValueError:
        return float('inf')
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.timestamp()


def next_job(dirs):
    """queued 중 createdAt이 가장 이른 요청(같으면 파일 이름 순) -> (파일 이름, 요청). 없으면 None."""
    queued = [(name, job) for name, job in list_jobs(dirs) if job.get('status') == 'queued']
    return min(queued, key=lambda item: (_created(item[1]), item[0])) if queued else None


def _fail(path, job, message):
    job.pop('profileKey', None)
    job.update(status='failed', stage='실패', progress=None, error=message, finishedAt=now_iso())
    write_json(path, job)


def recover(dirs):
    """작업자가 (다시) 시작할 때: running이던 요청을 MSG_RESTART로 닫고 work를 비운다. queued는 그대로 둔다."""
    for name, job in list_jobs(dirs):
        if job.get('status') == 'running':
            log.warning('진행 중이던 요청을 닫음(작업자 다시 시작): %s', name)
            _fail(os.path.join(dirs.jobs, name), job, MSG_RESTART)
    for entry in os.listdir(dirs.work):
        path = os.path.join(dirs.work, entry)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)


# ---------------- 요청 하나
def process(dirs, name, job, max_minutes, analyze_fn=None):
    """jobs/<name>의 요청(job) 하나를 분석해 끝 상태(done | failed)로 쓴다. analyze_fn은 시험용 자리(기본 analyze.analyze).
    -> 마지막으로 쓴 요청. name이 '<uuid v4>.json'이 아니면 아무것도 쓰지 않고 ValueError(jobs/ 밖에 쓰지 않게)."""
    if not (isinstance(name, str) and JOB_FILE.fullmatch(name)):
        raise ValueError('요청 파일 이름이 uuid v4 .json이 아님')
    path = os.path.join(dirs.jobs, name)
    job = dict(job)
    if not valid_job(job) or name != job['id'] + '.json':
        log.warning('요청 형식이 맞지 않음: %s', name)
        _fail(path, job, MSG_BAD_JOB)
        return job
    if not LOGIN.fullmatch(job['login']):
        log.warning('GitHub 아이디 형식이 맞지 않음: %s', name)
        _fail(path, job, MSG_BAD_LOGIN)
        return job
    for k in ('error', 'finishedAt', 'profileKey'):
        job.pop(k, None)
    job.update(status='running', stage='레포 찾기', progress=None, startedAt=now_iso())
    write_json(path, job)

    def progress(stage, done, total):
        job['stage'] = stage
        job['progress'] = None if done is None or total is None else {'done': done, 'total': total}
        write_json(path, job)

    request = {k: job[k] for k in ('id', 'namespace', 'subjectId', 'login', 'input', 'createdAt') if k in job}
    t0 = time.time()
    log.info('분석 시작 %s: login %s', job['id'], job['login'])
    try:
        profile = (analyze_fn or A.analyze)(request, dirs.work, t0 + max_minutes * 60, progress)
        if not isinstance(profile, dict):
            raise TypeError(f'분석 결과가 dict가 아님: {type(profile).__name__}')
        key = profile_key(job['namespace'], job['subjectId'])
        write_json(os.path.join(dirs.profiles, key + '.json'), profile)   # 프로필 먼저, 그다음 done(머리 설명)
    except (UserError, RateLimited) as e:
        log.warning('분석 실패 %s(%.0f초): %s', job['id'], time.time() - t0, e)
        _fail(path, job, str(e) or MSG_ERROR)
        return job
    except Exception:
        log.exception('분석 오류 %s(%.0f초)', job['id'], time.time() - t0)
        _fail(path, job, MSG_ERROR)
        return job
    job.update(status='done', stage='끝', progress=None, profileKey=key, finishedAt=now_iso())
    write_json(path, job)
    repos = profile.get('repos') if isinstance(profile.get('repos'), dict) else {}
    log.info('분석 끝 %s(%.0f초): 레포 찾음 %s, 분석 %s, 실패 %s', job['id'], time.time() - t0, repos.get('found'),
             repos.get('analyzed'), repos.get('failed'))
    return job


# ---------------- 자체 점검
def _py_version():
    return tuple(sys.version_info[:3])


def _git_version():
    """`git --version` → (판 튜플 또는 None, 출력 한 줄). git이 없거나 실패하면 None."""
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    try:
        p = subprocess.run(['git', '--version'], stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (p.stdout or '').strip()
    if p.returncode != 0 or not text:
        return None
    m = re.search(r'(\d+)\.(\d+)', text)
    return (tuple(int(x) for x in m.groups()) if m else None), text


def self_check(root, code_dir=HERE):
    """배포 전 점검(머리 설명). root = 데이터 폴더, code_dir = 서비스 폴더(시험용 자리). 문제가 없으면 'OK'를 찍고 0, 있으면
    '자체 점검 실패: …' 줄을 찍고 1. jobs·profiles·work는 읽기만 한다."""
    problems = []
    py = _py_version()
    if py < MIN_PYTHON:
        problems.append('Python %d.%d 이상이 필요합니다(지금 %s)' % (MIN_PYTHON + ('.'.join(map(str, py)),)))
    git = _git_version()
    log.info('자체 점검: Python %s, %s', '.'.join(map(str, py)), git[1] if git else 'git 없음')
    if git is None:
        problems.append('git을 실행하지 못했습니다')
    elif git[0] is None or git[0] < GIT_WANT:
        log.warning('%s: %d.%d보다 옛 판이거나 판을 읽지 못함. GIT_NO_LAZY_FETCH를 몰라 큰 레포에서 빠진 파일 내용을 받으러 갈 수'
                    ' 있습니다', git[1], *GIT_WANT)

    if not os.path.isdir(root):
        problems.append(f'데이터 폴더가 없습니다: {root}')
    else:
        try:
            fd, tmp = tempfile.mkstemp(dir=root, prefix='.self-check-', suffix='.tmp')
            os.close(fd)
            os.remove(tmp)
        except OSError as e:
            problems.append(f'데이터 폴더에 쓸 수 없습니다: {root} ({e.strerror})')
        for sub in ('jobs', 'profiles', 'work'):
            p = os.path.join(root, sub)
            if os.path.lexists(p) and not (os.path.isdir(p) and os.access(p, os.W_OK | os.X_OK)):
                problems.append(f'{sub} 폴더에 쓸 수 없습니다: {p}')

    ling = os.path.join(code_dir, 's2', 'data', 'linguist')
    for name in LINGUIST:
        p = os.path.join(ling, name)
        if not (os.path.isfile(p) and os.path.getsize(p) > 0):
            problems.append(f'Linguist 자료가 없거나 비어 있습니다: {os.path.relpath(p, code_dir)}')

    for dirpath, dirnames, filenames in os.walk(code_dir):
        dirnames[:] = sorted(d for d in dirnames if d != '__pycache__' and not d.startswith('.'))
        for f in sorted(filenames):
            if not f.endswith('.py'):
                continue
            p = os.path.join(dirpath, f)
            try:
                with open(p, 'rb') as fh:
                    compile(fh.read(), p, 'exec', dont_inherit=True)   # 메모리에서만(컴파일 파일을 쓰지 않음)
            except (SyntaxError, ValueError, OSError) as e:
                where = f' {e.lineno}줄' if getattr(e, 'lineno', None) else ''
                problems.append(f'문법 오류: {os.path.relpath(p, code_dir)}{where} ({type(e).__name__})')

    if problems:
        for p in problems:
            print('자체 점검 실패: ' + p)
        return 1
    print('OK')
    return 0


# ---------------- 실행
def _lock(root):
    """데이터 폴더의 .worker.lock을 잡는다(프로세스가 끝나면 풀림). -> 잡은 파일, 다른 작업자가 잡고 있으면 None."""
    f = open(os.path.join(root, LOCK), 'a')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def _setup_logging():
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='%(asctime)s %(levelname)s %(name)s: %(message)s')


def _positive(text):
    v = float(text)
    if not v > 0:
        raise argparse.ArgumentTypeError('0보다 커야 합니다')
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(description='lv-stat 스테이징 분석 작업자(CONTRACT.md)')
    ap.add_argument('--data-dir', required=True, help='<CAREER_DATA_DIR>/lv-stat')
    ap.add_argument('--once', action='store_true', help='대기 중인 요청 하나(있으면)만 처리하고 끝낸다')
    ap.add_argument('--max-minutes', type=_positive, default=MAX_MINUTES, help='요청 하나의 분석 시간 상한(분)')
    ap.add_argument('--poll', type=_positive, default=POLL_S, help='대기 중인 요청이 없을 때 다시 보는 간격(초)')
    ap.add_argument('--self-check', action='store_true', help='배포 전 점검(데이터는 고치지 않음)')
    args = ap.parse_args(argv)
    _setup_logging()
    root = os.path.abspath(args.data_dir)
    if args.self_check:
        return self_check(root)
    dirs = Dirs(root)
    lock = _lock(dirs.root)
    if lock is None:
        log.error('이 데이터 폴더에서 다른 작업자가 돌고 있어 멈춤: %s', dirs.root)
        return 1
    try:
        # s2lib는 이 프로세스에서 처음 쓸 때 LV_S2_HOME 아래 빈 HOME(.emptyhome)을 만든다. 코드 폴더 대신 work 아래에 두고,
        # analyze는 s2 자식 프로세스마다 LV_S2_HOME을 요청 폴더로 따로 준다.
        os.environ['LV_S2_HOME'] = dirs.work
        token = 'yes' if os.environ.get('LV_GITHUB_TOKEN', '').strip() else 'no'
        log.info('작업자 시작: 데이터 %s, token %s, 상한 %g분, 간격 %g초%s', dirs.root, token, args.max_minutes, args.poll,
                 ', 하나만' if args.once else '')
        recover(dirs)
        while True:
            found = next_job(dirs)
            if found:
                process(dirs, found[0], found[1], args.max_minutes)
            if args.once:
                return 0
            if not found:
                time.sleep(args.poll)
    finally:
        lock.close()


if __name__ == '__main__':
    sys.exit(main())
