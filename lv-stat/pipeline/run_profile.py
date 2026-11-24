#!/usr/bin/env python3
"""프로필 URL 하나로 끝까지: 공개 레포 목록 -> 포크 제외 -> clone.sh 로 받기 -> 레포마다 근거 묶음·packet·점검 -> stat 하나 -> 공고 매칭.

Usage:
  python3 pipeline/run_profile.py https://github.com/<계정> --name "<커밋에 쓰는 이름>" [--name ...] \\
      [--repo https://github.com/<다른 계정>/<레포> ...] --out out/profile
  규칙만(점검 없이) 돌리려면 --no-verify 를 붙인다.

하는 일
  1. GitHub 공개 API(토큰 없이)로 <계정>의 공개 레포 목록을 받고 포크를 뺀다. 다른 계정·조직 아래 레포는 목록에 안 나오므로 --repo 로 더한다.
  2. pipeline/clone.sh 로 --repos-dir(기본 career-stat-handoff/repos) 아래에 받는다. 받은 코드는 실행하지 않는다(빌드·설치·테스트 포함).
  3. 레포마다: bundle.py 로 근거 묶음(메모리에서만) -> identity.py 로 내 git 이름 고르기 -> 내 근거만으로 packet -> verify_agent.py 로 점검.
     packet 은 점검할 때만 메모리에 만들고 저장하지 않는다(--keep-packets 일 때만 저장).
  4. 레포마다 다른 내 git 이름을 --canonical(기본: 계정 이름) 하나로 맞춘 뒤 to_stat.build_stat() 에 bundle 을 모두 넣어 stat 하나를 만들고 match 한다.
  레포 하나가 실패하면 run.json 에 이유를 적고 다음 레포로 넘어간다. 내 이름이 확실하지 않은 레포는 stat 에서 빼고 후보 이름을 적는다.
  --also-branch develop 을 주면, 기본 브랜치에 아직 안 들어간 develop 끝도 '<레포>@develop' 이라는 별도 bundle 로 더한다(추출기는 HEAD 만 보므로 사본 폴더의 HEAD 를 옮겨서 읽음).

출력(--out 아래)
  run.json             레포별 처리 기록(실패·제외 이유 포함)          identity.json  레포별 이름 판단(이메일은 가림)
  repos/<계정__레포>/   bundle.mine.json(내 근거만·이름 맞춘 것. 내 git 이름이 둘이면 bundle.mine.1.json, .2.json), agent_output.json, verify_log.json, verdicts.json
                       다른 기여자의 근거는 저장하지 않는다(이름과 커밋 수만 run.json·identity.json 에 남음)
  verdicts.json        모든 레포의 점검 결과(to_stat.py --verdicts 형식)
  stat.json, match.json
표준 라이브러리만 쓴다(Python 3.9 이상).
"""
import argparse, atexit, hashlib, json, os, re, shutil, signal, subprocess, sys, tempfile, time
import urllib.error, urllib.request
sys.dont_write_bytecode = True                         # pipeline/__pycache__ 를 남기지 않는다(하위 프로세스에는 PYTHONDONTWRITEBYTECODE 로 넘김)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import identity as ID, make_packets as MP, match as MT, to_stat as ST, verify_agent as VA

OWNER_RX = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*')
REPO_RX = re.compile(r'[A-Za-z0-9._-]+')              # 레포 이름은 .github, _notes 처럼 시작할 수 있다
BRANCH_RX = re.compile(r'[A-Za-z0-9][A-Za-z0-9_./-]*')


def harden_env(repos_dir=None):
    """받기·분석 단계에 토큰이 쓰이지 않게 한다: 자격 증명 도우미가 든 시스템·전역 git 설정과 askpass 를 끄고, 빠진 blob 을 다시 받지 않게 한다.
    repos_dir 를 주면 git 이 그 폴더 위로 올라가 바깥 레포(이 프로젝트 자체)를 대신 읽지 못하게 막는다."""
    for k in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_NAMESPACE', 'GIT_SSL_NO_VERIFY',
              'GIT_NO_REPLACE_OBJECTS', 'GIT_CONFIG', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS'): os.environ.pop(k, None)      # 물려받은 값이 다른 저장소를 읽게 하거나 검증을 끄지 못하게
    os.environ.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0', GIT_ASKPASS='', SSH_ASKPASS='', GIT_NO_LAZY_FETCH='1', GIT_LFS_SKIP_SMUDGE='1')
    if repos_dir: os.environ['GIT_CEILING_DIRECTORIES'] = os.pathsep.join(dict.fromkeys([os.path.abspath(repos_dir), os.path.realpath(repos_dir)]))
    for k in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN', 'NETRC',
              'ANTHROPIC_API_KEY'): os.environ.pop(k, None)        # 점검용 키는 이미 읽어 둠: git·bundle.py 같은 자식 프로세스에는 넘기지 않는다


_HOME = []


def empty_home():
    """받기 때 쓸 빈 HOME 폴더: git(libcurl)이 ~/.netrc 에 저장된 암호를 쓰지 못하게 한다. 끝날 때 지운다."""
    if not _HOME:
        _HOME.append(tempfile.mkdtemp(prefix='career-clone-home-'))
        atexit.register(shutil.rmtree, _HOME[0], True)
    return _HOME[0]


def run_cmd(cmd, timeout, env=None):
    """명령을 새 프로세스 묶음으로 돌리고, 시간이 넘으면 묶음째 끝낸다. -> (종료 코드, stdout, stderr)"""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', env=env, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except BaseException as e:                   # 시간 초과뿐 아니라 Ctrl-C 등으로 빠져나갈 때도 자식 묶음을 남기지 않는다
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        if isinstance(e, subprocess.TimeoutExpired): raise TimeoutError(f'{timeout:.0f}초 안에 끝나지 않음')
        raise
    return p.returncode, out, err


def git(repo, *args):
    r = subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, r.stdout.strip()


def dump(path, obj):
    with open(path, 'w', encoding='utf-8') as f: json.dump(obj, f, ensure_ascii=False, indent=1)


def load(path):
    with open(path, encoding='utf-8') as f: return json.load(f)


def parse_login(s):
    m = re.fullmatch(r'(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/?', s.strip()) or re.fullmatch(r'([^/\s]+)', s.strip())
    if not m or not OWNER_RX.fullmatch(m.group(1)): sys.exit(f'프로필 URL 을 읽을 수 없음: {s} (예: https://github.com/<계정>)')
    return m.group(1)


def parse_repo(s):
    """레포 URL 또는 owner/repo -> 'owner/repo'. 이름에 허용 문자만 있는지 확인(셸·경로로 그대로 넘어가므로)"""
    m = re.fullmatch(r'(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?(?:[#?].*)?', s.strip()) or re.fullmatch(r'([^/\s]+)/([^/\s]+?)(?:\.git)?', s.strip())
    if not m or not OWNER_RX.fullmatch(m.group(1)) or not REPO_RX.fullmatch(m.group(2)) or m.group(2) in ('.', '..'): raise ValueError(f'레포 주소를 읽을 수 없음: {s}')
    return f'{m.group(1)}/{m.group(2)}'


def gh(path, ctx):
    """GitHub 공개 API. 토큰을 넣지 않는다(시간당 60회)."""
    req = urllib.request.Request('https://api.github.com' + path, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'profile-repo-lister'})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read().decode('utf-8'))


def list_repos(login, ctx):
    out = []
    for page in range(1, 31):
        d = gh(f'/users/{login}/repos?per_page=100&page={page}&type=owner&sort=full_name', ctx)
        out += d
        if len(d) < 100: break
    return sorted(out, key=lambda r: r['full_name'].lower())


def is_repo_root(d):
    """d 자체가 받은 레포인가(.git 이 있고 HEAD 가 커밋인가). git 이 위 폴더의 다른 레포를 찾아 쓰는 일을 막는다."""
    return os.path.isdir(os.path.join(d, '.git')) and git(d, 'rev-parse', '-q', '--verify', 'HEAD^{commit}')[0] == 0


def clone(full, repos_dir, timeout):
    """clone.sh 로 받기 -> (폴더, 이미 있었나). 실패하면 RuntimeError(이유)"""
    d = os.path.join(repos_dir, full.replace('/', '__', 1))
    existed, tail = os.path.lexists(d), ''
    if not existed:
        try:
            rc, out, err = run_cmd(['bash', os.path.join(HERE, 'clone.sh'), repos_dir, full], timeout, env=dict(os.environ, HOME=empty_home()))
            tail = ' / '.join(x.strip() for x in (out + '\n' + err).splitlines() if x.strip())[-300:]
        except TimeoutError as e:
            tail = f'받기가 {e}'
    if is_repo_root(d): return d, existed
    if existed: raise RuntimeError(f'이미 있는 폴더 {os.path.basename(d)} 가 온전한 clone 이 아님(.git 이나 커밋이 없음). 그 폴더를 지우고 다시 실행')
    shutil.rmtree(d, ignore_errors=True)          # 이번 실행이 만들다 만 폴더만 치운다(다음 실행에서 다시 받게)
    raise RuntimeError(('받기 실패' if not tail else f'받기 실패: {tail}') + ' (빈 레포이면 커밋이 없어 분석할 수 없음)')


def branch_copy(repo_dir, branch, repos_dir):
    """기본 브랜치에 아직 안 들어간 브랜치 끝을 HEAD 로 둔 사본 폴더(추출기는 HEAD 만 본다). 브랜치가 없거나 이미 HEAD 에 들어 있으면 None. 원본 clone 은 바꾸지 않는다."""
    rc, sha = git(repo_dir, 'rev-parse', '-q', '--verify', f'refs/remotes/origin/{branch}^{{commit}}')
    if rc != 0 or not sha: return None
    if git(repo_dir, 'merge-base', '--is-ancestor', sha, 'HEAD')[0] == 0: return None
    dst = os.path.join(repos_dir, '_branch', branch.replace('/', '__'), os.path.basename(repo_dir))     # 폴더 이름은 원본과 같게(연습 레포 판정이 폴더 이름을 봄)
    if not os.path.isdir(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copytree(repo_dir, dst, symlinks=True)
    if not os.path.isdir(os.path.join(dst, '.git')) or git(dst, 'update-ref', '--no-deref', 'HEAD', sha)[0] != 0: raise RuntimeError(f'사본의 HEAD 를 {branch} 로 옮기지 못함')
    return dst


def make_bundle(repo_dir, label, timeout):
    """bundle.py 를 따로 띄워 근거 묶음을 만든다(한 레포가 죽거나 멈춰도 전체가 멈추지 않게)."""
    rc, out, err = run_cmd([sys.executable, os.path.join(HERE, 'bundle.py'), repo_dir, '--name', label], timeout, env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1'))
    if rc != 0:
        lines = [x for x in err.strip().splitlines() if x.strip()]
        raise RuntimeError('bundle.py 실패: ' + (lines[-1][:300] if lines else f'종료 코드 {rc}'))
    return json.loads(out)


def verify_cached(packets, odir, a, key, label):
    """같은 packet·지시문·모델로 이미 받은 답이 있으면 다시 부르지 않는다. -> (agent_output, info, 다시 썼나)"""
    ap, lp = os.path.join(odir, 'agent_output.json'), os.path.join(odir, 'verify_log.json')
    h = hashlib.sha256(json.dumps(packets, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    with open(os.path.join(HERE, 'verifier_prompt.md'), encoding='utf-8') as f: ph = hashlib.sha256(f.read().encode('utf-8')).hexdigest()
    if os.path.exists(ap) and os.path.exists(lp):
        try:
            old, prev = load(lp), load(ap)
        except (OSError, ValueError):                # 깨진 파일은 저장된 답이 없는 것으로 본다
            old = prev = None
        if isinstance(old, dict) and isinstance(prev, list) and old.get('complete') and (old.get('packets_sha256'), old.get('prompt_sha256'), old.get('model'), old.get('effort')) == (h, ph, a.model, a.effort):
            return prev, old, True
    out, info = VA.verify(packets, key, model=a.model, effort=a.effort, cap_usd=a.cap_usd, ledger=a.ledger, source=label, retry_malformed=getattr(a, 'retry_malformed', 0), log=lambda s: print('  ' + s.strip()))
    dump(ap, out); dump(lp, info)
    return out, info, False


def process(rec, repo_dir, odir, a, key, login, canonical):
    """레포(또는 그 레포의 다른 브랜치) 하나를 처리해 rec 를 채운다. -> (내 근거만 든 bundle 목록, 점검 결과 줄들). 어느 단계에서 죽었는지는 rec['stage']
    한 레포에 내 git 이름이 둘 이상이면 이름마다 bundle 을 따로 만든다(라벨 '<레포>#<git 이름>'). 같은 활동이 양쪽에 있어도 판정이 근거마다 따로 적용된다."""
    rec['stage'] = '근거 묶음(bundle.py)'
    if not is_repo_root(repo_dir): raise RuntimeError('받은 레포 폴더가 아님(.git 이나 커밋이 없음)')
    bundle = make_bundle(repo_dir, rec['label'], a.timeout)      # 모든 기여자의 근거가 들어 있다. 통째로는 저장하지 않고 내 것만 남긴다
    rec.update(head=bundle['meta']['head'], people=bundle['meta']['people'], practice=bundle['meta']['practice'])
    if a.keep_full_bundle:
        os.makedirs(odir, exist_ok=True); dump(os.path.join(odir, 'bundle.json'), bundle)
    if not a.keep_packets and os.path.exists(os.path.join(odir, 'packets.json')): os.remove(os.path.join(odir, 'packets.json'))     # 예전 --keep-packets 실행이 남긴 코드 조각
    rec['stage'] = '이름 잇기(identity.py)'
    idr = ID.resolve(repo_dir, login, a.name, a.email)
    rec.update(identity=idr['status'], mine=idr['mine'], candidates=idr['candidates'], _identity=idr)
    mine = [m for m in idr['mine'] if m in bundle['meta']['people']]
    rec['others'] = len(bundle['meta']['people']) - len(mine)
    if not mine:
        rec.update(status='excluded', reason=idr.get('note') or ('내 이름으로 볼 근거가 없음(기여자 이름만 있음)' if idr['status'] == 'none' else '내 이름인지 확실하지 않음(후보만 있음)'))
        return [], []
    rec['stage'] = 'packet 만들기(make_packets.py)'
    os.makedirs(odir, exist_ok=True)
    label_of = {m: rec['label'] if len(mine) == 1 else f"{rec['label']}#{m}" for m in mine}
    packets = []
    for m in mine:
        for p in MP.from_bundle(dict(bundle, evidence=[e for e in bundle['evidence'] if e['person'] == m]), repo_dir):
            p['id'] = f'{len(packets):04d}'; packets.append(p)                          # 내 이름이 둘이어도 id 가 겹치지 않게 이어서 매김
    rec.update(evidence=sum(1 for e in bundle['evidence'] if e['person'] in mine), packets=len(packets))
    if a.keep_packets: dump(os.path.join(odir, 'packets.json'), packets)
    rows = []
    if a.no_verify: rec.update(verify='점검 안 함(--no-verify)', answered=0)
    elif not packets: rec.update(verify='점검 대상 없음', answered=0)
    else:
        rec['stage'] = '점검(verify_agent.py)'
        out, info, cached = verify_cached(packets, odir, a, key, rec['label'])
        byid = {x['id']: x for x in out}
        for p in packets:
            v = byid.get(p['id'])
            rows.append(dict(repo=label_of[p['person']], person=canonical, key=p['judgment'], verdict=v['verdict'] if v else 'unsure', reason_code=v['reason_code'] if v else None, reason=v['reason'] if v else '',
                             git_name=p['person'], lv=p['lv'], evidence=p['evidence'], answered=bool(v)))
        state = '저장된 답 다시 씀' if cached else '점검함'
        if not info.get('complete'):
            dropped = any((b.get('outcome') or '').startswith('응답 버림') or any(t.get('dropped_items') for t in b.get('tries') or [] if isinstance(t, dict)) for b in info.get('batches') or [])
            state = ('점검 일부 실패(답을 못 받은 판정은 모름으로 처리)' if info.get('failed_calls') or info.get('stopped')
                     else '점검함(버린 응답이 있어 답 없는 판정은 모름으로 처리)' if dropped else '점검함(모델이 답하지 않은 판정은 모름으로 처리)')
        rec.update(verify=state, answered=sum(1 for r in rows if r['answered']),
                   missing=sum(1 for r in rows if not r['answered']), verdicts={v: sum(1 for r in rows if r['verdict'] == v) for v in VA.VERDICTS}, usd=0.0 if cached else info.get('usd'),
                   verify_stopped=info.get('stopped'))
        dump(os.path.join(odir, 'verdicts.json'), rows)
    rec['stage'] = '내 근거만 모으기'
    for old in os.listdir(odir):                       # 이전 실행이 남긴 내 근거 파일(이름 수가 달라졌을 수 있음)
        if re.fullmatch(r'bundle\.mine(\.\d+)?\.json', old): os.remove(os.path.join(odir, old))
    mbs, files = [], []
    for n, m in enumerate(mine):
        meta = dict(bundle['meta'], repo=label_of[m], people=[m], merged={k: v for k, v in (bundle['meta'].get('merged') or {}).items() if k == m},
                    ai_commits={k: v for k, v in (bundle['meta'].get('ai_commits') or {}).items() if k == m})        # 남의 이름·집계는 남기지 않는다
        mb = dict(meta=meta, evidence=[dict(e, person=canonical) for e in bundle['evidence'] if e['person'] == m],
                  weak=[dict(w, person=canonical) for w in bundle.get('weak', []) if w['person'] == m])
        f = os.path.join(odir, 'bundle.mine.json' if len(mine) == 1 else f'bundle.mine.{n + 1}.json')
        dump(f, mb); mbs.append(mb); files.append(f)
    rec.update(status='ok', stage=None, _files=files)
    return mbs, rows


def main():
    ap = argparse.ArgumentParser(description='GitHub 프로필 URL -> 공개 레포 전부 -> stat 하나 -> 공고 매칭', formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('profile', help='https://github.com/<계정>')
    ap.add_argument('--repo', action='append', default=[], help='다른 계정·조직 아래의 레포 URL(여러 번 줄 수 있음). 포크여도 직접 준 것은 넣는다')
    ap.add_argument('--name', action='append', default=[], help='내가 커밋에 쓰는 git 이름(여러 번). 계정 이름과 같아도 적어 줘야 한다')
    ap.add_argument('--email', action='append', default=[], help='내 커밋 이메일(선택, 여러 번)')
    ap.add_argument('--canonical', help='stat 에 쓸 사람 이름(기본: 계정 이름)')
    ap.add_argument('--out', required=True); ap.add_argument('--repos-dir', default=os.path.join(ROOT, 'repos'))
    ap.add_argument('--postings', default=os.path.join(ROOT, 'data', 'postings.json'))
    ap.add_argument('--no-verify', action='store_true', help='점검 에이전트 없이 규칙만(LV3 이상 활동을 점검 없이 통과로 봄)')
    ap.add_argument('--include-forks', action='store_true'); ap.add_argument('--also-branch', action='append', default=[], help='기본 브랜치에 안 들어간 이 브랜치 끝도 따로 분석(예: develop)')
    ap.add_argument('--keep-packets', action='store_true', help='packets.json 을 지우지 않고 남김(코드 조각이 들어 있음)')
    ap.add_argument('--keep-full-bundle', action='store_true', help='bundle.py 가 낸 bundle.json 을 통째로 남김(다른 기여자의 근거도 들어 있음. 귀속을 확인할 때)')
    ap.add_argument('--model', default=VA.MODEL); ap.add_argument('--effort', default=VA.EFFORT); ap.add_argument('--cap-usd', type=float, default=1.0)
    ap.add_argument('--retry-malformed', type=int, default=0, help='점검 응답의 형식이 깨졌을 때 다시 받아 보는 횟수(기본 0: 버리고 답 없는 판정은 모름으로)')
    ap.add_argument('--ledger', default=os.path.join(ROOT, 'out', 'verifier_spend.json')); ap.add_argument('--env-file', default=os.path.join(ROOT, '.env'))
    ap.add_argument('--timeout', type=float, default=1800, help='레포 하나의 받기·분석 시간 한도(초)')
    a = ap.parse_args()
    login = parse_login(a.profile); canonical = a.canonical or login
    for br in a.also_branch:
        if not BRANCH_RX.fullmatch(br) or '..' in br: ap.error(f'브랜치 이름을 읽을 수 없음: {br}')
    if not a.name and not a.email: print('주의: --name/--email 이 없어서 계정의 noreply 이메일로 올린 커밋만 내 것으로 본다', file=sys.stderr)
    key = None
    if not a.no_verify:
        if a.retry_malformed < 0: ap.error('--retry-malformed 는 0 이상이어야 함')
        if a.cap_usd and a.model not in VA.PRICE: ap.error(f'가격표(verify_agent.PRICE)에 없는 모델 {a.model}: 비용 한도를 계산할 수 없음. --cap-usd 0 을 주면 한도 검사 없이 부름')
        key, _ = VA.load_key(a.env_file)
        if not key: sys.exit('ANTHROPIC_API_KEY 가 환경 변수에도 .env 에도 없음. 점검 없이 규칙만 돌리려면 --no-verify')
        if not VA.KEY_RX.fullmatch(key): sys.exit('ANTHROPIC_API_KEY 값에 공백·줄바꿈·ASCII 밖 글자가 있음(값은 찍지 않음). 점검 없이 규칙만 돌리려면 --no-verify')
    out = os.path.abspath(a.out); repos_dir = os.path.abspath(a.repos_dir)
    postings = load(a.postings)                    # 공고 파일이 없으면 레포를 돌기 전에 멈춘다
    harden_env(repos_dir)
    os.makedirs(os.path.join(out, 'repos'), exist_ok=True); os.makedirs(repos_dir, exist_ok=True)
    ctx = VA.ssl_context()
    run = dict(profile=login, canonical=canonical, names=a.name, n_emails=len(a.email), verify=not a.no_verify, model=None if a.no_verify else a.model, effort=None if a.no_verify else a.effort,
               also_branch=a.also_branch, started=time.strftime('%Y-%m-%dT%H:%M:%S%z'), python=sys.version.split()[0], listing=None, skipped=[], targets=[])
    dump(os.path.join(out, 'run.json'), run)       # 끝나기 전에는 finished 가 없다: 중간에 죽으면 make_report 가 이 폴더로 표를 만들지 않는다
    # 1) 레포 목록 ----------------------------------------------------------------
    todo, seen = [], set()
    try:
        lst = list_repos(login, ctx)
        run['listing'] = dict(ok=True, n=len(lst))
        for r in lst:
            full = r.get('full_name') or ''
            try:
                full = parse_repo(full)
            except ValueError as e:
                run['skipped'].append(dict(repo=full, reason=str(e))); continue
            if r.get('private'): run['skipped'].append(dict(repo=full, reason='비공개')); continue
            if r.get('fork') and not a.include_forks: run['skipped'].append(dict(repo=full, reason='포크')); continue
            todo.append(dict(repo=full, source='profile', size_kb=r.get('size'), default_branch=r.get('default_branch'), pushed_at=r.get('pushed_at'))); seen.add(full.lower())
    except Exception as e:                     # 목록을 못 받아도 --repo 로 준 레포는 계속한다
        run['listing'] = dict(ok=False, error=f'{type(e).__name__}: {e}'[:300])
        print(f"레포 목록을 받지 못함: {run['listing']['error']}", file=sys.stderr)
    for u in a.repo:
        try:
            full = parse_repo(u)
        except ValueError as e:
            run['skipped'].append(dict(repo=u, reason=str(e))); continue
        if full.lower() in seen: continue
        seen.add(full.lower()); t = dict(repo=full, source='extra')
        try:
            meta = gh(f'/repos/{full}', ctx)
            if meta.get('private'): run['skipped'].append(dict(repo=full, reason='비공개(공개 레포만 받음)')); continue
            t.update(fork=meta.get('fork'), size_kb=meta.get('size'), default_branch=meta.get('default_branch'), pushed_at=meta.get('pushed_at'))
        except urllib.error.HTTPError as e:
            if e.code == 404: run['skipped'].append(dict(repo=full, reason='없거나 비공개(공개 레포만 받음)')); continue
            t['meta_error'] = f'HTTP {e.code}'           # 조회 한도 등: 자격 증명 없이 받기 때문에 공개 레포만 받아진다
        except Exception as e:
            t['meta_error'] = type(e).__name__
        todo.append(t)
    print(f"대상 레포 {len(todo)}개, 건너뜀 {len(run['skipped'])}개" + (f" ({', '.join(s['repo'] + ': ' + s['reason'] for s in run['skipped'])})" if run['skipped'] else ''))
    # 2) 레포마다 -----------------------------------------------------------------
    bundles, rows_all, idents = [], [], {}
    for t in todo:
        full = t['repo']; slug = full.replace('/', '__', 1)
        base = dict(t, label=full, branch=None, status='failed', stage='받기(clone.sh)')
        run['targets'].append(base)
        try:
            repo_dir, existed = clone(full, repos_dir, a.timeout)
            base.update(dir=os.path.relpath(repo_dir, ROOT), clone='이미 있던 폴더를 씀(다시 받지 않음)' if existed else '새로 받음')
        except Exception as e:
            base['reason'] = f'{type(e).__name__}: {e}'[:400]; print(f"[실패] {full}: {base['stage']}: {base['reason']}"); continue
        jobs = [(base, repo_dir, os.path.join(out, 'repos', slug))]
        for br in a.also_branch:
            try:
                alt = branch_copy(repo_dir, br, repos_dir)
            except Exception as e:
                run['targets'].append(dict(repo=full, label=f'{full}@{br}', branch=br, source=t['source'], status='failed', stage='브랜치 사본 만들기', reason=f'{type(e).__name__}: {e}'[:400])); continue
            if alt:
                rec = dict(repo=full, label=f'{full}@{br}', branch=br, source=t['source'], status='failed', dir=os.path.relpath(alt, ROOT))
                run['targets'].append(rec); jobs.append((rec, alt, os.path.join(out, 'repos', f'{slug}@{br.replace("/", "__")}')))
        for rec, rdir, odir in jobs:
            try:
                mbs, rows = process(rec, rdir, odir, a, key, login, canonical)
            except VA.Unavailable as e:              # 점검을 쓸 수 없음: 여기서 멈추고 표시를 남긴다(stat·match 는 만들지 않음)
                if '_identity' in rec: idents[rec['label']] = rec.pop('_identity')
                rec.update(status='failed', reason=f'점검 호출을 쓸 수 없음: {e}'[:400])
                run['aborted'] = f"점검 호출을 쓸 수 없음({rec['label']}): {e}"[:400]
                dump(os.path.join(out, 'run.json'), run)
                sys.exit(run['aborted'] + '\n일시 오류면 같은 명령을 다시 실행한다(끝난 레포는 저장된 답을 씀). 점검 없이 규칙만 돌리려면 같은 명령에 --no-verify')
            except Exception as e:
                rec.update(status='failed', reason=f'{type(e).__name__}: {e}'[:400]); print(f"[실패] {rec['label']}: {rec.get('stage')}: {rec['reason']}"); continue
            finally:
                if '_identity' in rec: idents[rec['label']] = rec.pop('_identity')
                if rec.get('status') != 'ok': rec.pop('_files', None)
            if not mbs:
                print(f"[제외] {rec['label']}: {rec['reason']} | 기여자 {rec.get('people')} | 후보 {rec.get('candidates')}"); continue
            bundles += mbs; rows_all += rows; rec['stat_inputs'] = [os.path.relpath(f, out) for f in rec.pop('_files')]     # --out 기준 경로
            v = rec.get('verdicts')
            print(f"[완료] {rec['label']} @{rec['head'][:7]}: 내 이름 {rec['mine']} | 근거 {rec['evidence']}건 | 점검 대상 {rec['packets']}건"
                  + (f" -> 통과 {v['pass']} / 기각 {v['reject']} / 모름 {v['unsure']}" if v else f" ({rec['verify']})"))
    # 3) stat 하나, 공고 매칭 -------------------------------------------------------
    verd = {(r['repo'], r['person'], r['key']): r['verdict'] for r in rows_all}
    stat = ST.build_stat(bundles, canonical, verd)
    res = MT.match_all(stat, postings)
    dump(os.path.join(out, 'identity.json'), idents); dump(os.path.join(out, 'verdicts.json'), rows_all)
    dump(os.path.join(out, 'stat.json'), stat); dump(os.path.join(out, 'match.json'), res)
    ok = [r for r in run['targets'] if r['status'] == 'ok']
    run.update(finished=time.strftime('%Y-%m-%dT%H:%M:%S%z'), stat_inputs=[f for r in ok for f in r['stat_inputs']], n_ok=len(ok), n_failed=sum(1 for r in run['targets'] if r['status'] == 'failed'),
               n_excluded=sum(1 for r in run['targets'] if r['status'] == 'excluded'), stat_keys=len(stat['stat']), weak_keys=len(stat['weak']),
               usd=round(sum(r.get('usd') or 0 for r in run['targets']), 6))
    dump(os.path.join(out, 'run.json'), run)
    top = res['postings'][0] if res['postings'] else None
    print(f"레포 {len(run['targets'])}개 중 stat 에 넣은 것 {run['n_ok']}개, 실패 {run['n_failed']}개, 이름 불확실로 뺀 것 {run['n_excluded']}개 | stat 키 {len(stat['stat'])}개, 정황 {len(stat['weak'])}개"
          + (f" | 가장 잘 맞는 공고: {top['company']} / {top['title'][:30]} ({top['summary']})" if top else '') + f"\n결과: {out}")
    if not run['targets'] and not (run['listing'] or {}).get('ok'): sys.exit(1)


if __name__ == '__main__':
    main()
