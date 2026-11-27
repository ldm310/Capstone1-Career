"""lv-stat 2단계 변수 점검용 공통 부품. 버림용 스파이크(제품 코드 아님, 2026-11-26).
2단계 스파이크를 스테이징 서비스로 옮김(2026-11-27).

- 받은 레포는 읽기만 한다(git plumbing). 실행·빌드·설치·시험하지 않는다.
- 작업 폴더 S2 = 환경 변수 LV_S2_HOME(요청마다 따로), 없으면 코드 폴더. people.json·index/·out/·.emptyhome/이 그 아래다.
  불러올 때 정하므로 LV_S2_HOME은 불러오기 전에 절대 경로로 둔다(git -C가 폴더를 바꾸므로 HOME이 상대 경로면 안 됨).
  Linguist 자료(data/linguist/)는 코드 폴더에서 읽는다.
- 사람·레포 색인은 <S2>/index/<pid>/<repo_key>.json (s2_index.py가 만든다).
- git 자식 프로세스에는 토큰을 넘기지 않는다(GENV). GENV는 빠진 파일 내용 받기(lazy fetch)를 막는다(GIT_NO_LAZY_FETCH=1).
  <레포>/.git/lv-allow-lazy가 있는 레포는 git()의 모든 호출에 lazy fetch를 허용한다. 그래서 빠진 내용이 있으면
  log --numstat은 커밋마다, cat-file --batch-check는 빠진 파일마다 받으러 간다(내 커밋이 바꾼 파일만 받지 않는다).
  s2_index의 git_lazy(2단계 코드 그대로)는 표시가 없어도 numstat이 실패하면 lazy fetch를 허용해 다시 부른다.
- 카테고리 추출기는 load_person(pid)로 색인을 읽고, Repo.text()로 파일을 읽는다.
"""
import datetime
import functools
import json
import os
import re
import subprocess

CODE = os.path.dirname(os.path.abspath(__file__))
S2 = os.environ.get('LV_S2_HOME') or CODE
INDEX = os.path.join(S2, 'index')
OUT = os.path.join(S2, 'out')
LINGUIST = os.path.join(CODE, 'data', 'linguist', 'languages.yml')
EMPTY_HOME = os.path.join(S2, '.emptyhome')
os.makedirs(EMPTY_HOME, exist_ok=True)
# git 자식 프로세스에 넘기지 않는 비밀값. 토큰은 같은 프로세스의 GitHub API 부품(ghapi)만 os.environ에서 읽는다.
SECRET_ENV = ('LV_GITHUB_TOKEN', 'GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN', 'ANTHROPIC_API_KEY')
GENV = dict({k: v for k, v in os.environ.items() if k not in SECRET_ENV},
            GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1', GIT_NO_LAZY_FETCH='1',
            GIT_CONFIG_NOSYSTEM='1', HOME=EMPTY_HOME, XDG_CONFIG_HOME=EMPTY_HOME, GIT_ASKPASS='/usr/bin/false')
LAZY_MARK = 'lv-allow-lazy'      # <레포>/.git/ 아래 표시 파일. 큰 레포를 --filter=blob:none으로 받는 쪽이 만든다
KST = datetime.timezone(datetime.timedelta(hours=9))


def git(d, *a, inp=None, timeout=600, check=False):
    env = GENV
    if os.path.exists(os.path.join(d, '.git', LAZY_MARK)):       # 표시한 레포만 빠진 파일 내용을 받으러 간다
        env = {k: v for k, v in GENV.items() if k != 'GIT_NO_LAZY_FETCH'}
    p = subprocess.run(['git', '-C', d, '-c', 'core.hooksPath=/dev/null', '-c', 'core.quotePath=false', *a], input=inp, capture_output=True, env=env, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f'git {a[:2]} 실패: {p.stderr.decode(errors="replace")[:200]}')
    return p.returncode, p.stdout


# ---------------- 언어·파일 종류 (Linguist languages.yml, MIT)
@functools.lru_cache(maxsize=1)
def linguist():
    """-> (ext → (언어, 종류), 파일 이름 → (언어, 종류)). 그룹이 있으면 그룹 이름(TSX → TypeScript)."""
    langs, cur = {}, None
    key = None
    for line in open(LINGUIST, encoding='utf-8'):
        if not line.strip() or line.lstrip().startswith('#') or line.startswith('---'):
            continue
        if not line.startswith(' '):
            cur = line.rstrip().rstrip(':').strip('"')
            langs[cur] = dict(type=None, group=None, extensions=[], filenames=[])
            key = None
            continue
        s = line.strip()
        m = re.match(r'^(\w+):\s*(.*)$', s)
        if m and line.startswith('  ') and not line.startswith('   '):
            key = m.group(1)
            if key in ('type', 'group'):
                langs[cur][key] = m.group(2).strip().strip('"')
            continue
        m = re.match(r'^-\s+"?(.*?)"?$', s)
        if m and key in ('extensions', 'filenames'):
            langs[cur][key].append(m.group(1))
    by_ext, by_name = {}, {}
    for name, v in langs.items():
        tag = (v['group'] or name, v['type'])
        for e in v['extensions']:
            by_ext.setdefault(e.lower(), tag)       # 처음 나온 언어를 쓴다(겹치는 확장자는 아래에서 고침)
        for f in v['filenames']:
            by_name.setdefault(f, tag)
    fix = {'.h': ('C', 'programming'), '.ts': ('TypeScript', 'programming'), '.md': ('Markdown', 'prose'),
           '.sql': ('SQL', 'data'), '.yml': ('YAML', 'data'), '.yaml': ('YAML', 'data'), '.json': ('JSON', 'data'),
           '.pl': ('Perl', 'programming'), '.m': ('Objective-C', 'programming'), '.r': ('R', 'programming'),
           '.vue': ('Vue', 'markup'), '.svelte': ('Svelte', 'markup'), '.ipynb': ('Jupyter Notebook', 'markup'),
           '.kt': ('Kotlin', 'programming'), '.kts': ('Kotlin', 'programming'), '.cs': ('C#', 'programming'),
           '.fs': ('F#', 'programming'), '.html': ('HTML', 'markup'), '.css': ('CSS', 'markup'), '.scss': ('SCSS', 'markup'),
           '.tsx': ('TypeScript', 'programming'), '.jsx': ('JavaScript', 'programming'), '.mjs': ('JavaScript', 'programming'),
           '.cjs': ('JavaScript', 'programming'), '.toml': ('TOML', 'data'), '.xml': ('XML', 'data'), '.txt': ('Text', 'prose'),
           '.sh': ('Shell', 'programming'), '.dart': ('Dart', 'programming'), '.swift': ('Swift', 'programming'),
           '.go': ('Go', 'programming'), '.rs': ('Rust', 'programming'), '.java': ('Java', 'programming'),
           '.py': ('Python', 'programming'), '.rb': ('Ruby', 'programming'), '.php': ('PHP', 'programming'),
           '.scala': ('Scala', 'programming'), '.c': ('C', 'programming'), '.cpp': ('C++', 'programming'), '.cc': ('C++', 'programming'),
           '.hpp': ('C++', 'programming'), '.js': ('JavaScript', 'programming'), '.gradle': ('Gradle', 'data'),
           '.prisma': ('Prisma', 'data'), '.graphql': ('GraphQL', 'data'), '.tf': ('HCL', 'programming')}
    by_ext.update(fix)
    return by_ext, by_name


# 프로그래밍 활용에서 언어로 세지 않는 'programming' 종류(설정·빌드 언어)
NOT_A_LANGUAGE = {'Dockerfile', 'Makefile', 'CMake', 'Starlark', 'Nix', 'HCL', 'Jsonnet', 'Batchfile', 'Gradle', 'Procfile',
                  'Smarty', 'Mustache', 'Handlebars', 'Twig', 'Jinja', 'Groovy', 'Gnuplot', 'Vim Script', 'Emacs Lisp'}

VENDOR = re.compile(r'(^|/)(node_modules|vendor|bower_components|third_party|external|\.yarn|\.pnpm-store|site-packages|\.venv|venv|env|'
                    r'Pods|Carthage|DerivedData|\.gradle|\.idea|\.vscode|\.mvn|gradle/wrapper)(/|$)')
GENERATED = re.compile(r'^([^/]+/)?(dist|build|out|target|bin|obj)/|(^|/)(coverage|\.next|\.nuxt|\.svelte-kit|\.output|__pycache__|generated|\.dart_tool|out/production)(/|$)'
                       r'|(^|/)[^/]+[.-][0-9a-f]{8,}(\.chunk)?\.(js|mjs|css)$|(^|/)chunk-vendors[^/]*\.(js|css)$'
                       r'|\.min\.(js|css)$|\.bundle\.js$|\.map$|(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Pipfile\.lock|'
                       r'Cargo\.lock|composer\.lock|Gemfile\.lock|go\.sum|gradlew(\.bat)?|mvnw(\.cmd)?)$|\.pb\.go$|_pb2\.py$|\.g\.dart$|\.freezed\.dart$', re.I)
TEST = re.compile(r'(^|/)(test|tests|__tests__|spec|specs|e2e|cypress|androidTest|testFixtures|__mocks__|mocks?|fixtures?)(/|$)'
                  r'|\.(test|spec)\.[cm]?[jt]sx?$|_test\.(py|go|rb|dart)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs|swift)$|(^|/)tests?\.py$|\.spec\.dart$', re.I)
DOC = re.compile(r'\.(md|mdx|rst|adoc|txt)$|(^|/)(docs?|documentation)/', re.I)
MIGRATION = re.compile(r'(^|/)(migrations?|db/migrate|flyway|liquibase|alembic/versions|prisma/migrations)(/|$)|(^|/)V\d+(_\d+)*__[^/]+\.sql$', re.I)
CONFIG_NAME = re.compile(r'(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose\.ya?ml|\.github/workflows/[^/]+\.ya?ml|'
                         r'application[^/]*\.(ya?ml|properties)|settings\.py|\.env\.example|nginx[^/]*\.conf|Procfile|'
                         r'vercel\.json|netlify\.toml|fly\.toml|render\.yaml|app\.yaml|appspec\.yml|railway\.json|amplify\.yml|firebase\.json|'
                         r'serverless\.ya?ml|template\.ya?ml|k8s/[^/]+\.ya?ml|kubernetes/[^/]+\.ya?ml|helm/.*|\.gitlab-ci\.yml|Jenkinsfile|'
                         r'package\.json|pom\.xml|build\.gradle(\.kts)?|requirements[^/]*\.txt|pyproject\.toml|setup\.py|Pipfile|go\.mod|Cargo\.toml|'
                         r'dbt_project\.yml|profiles\.yml|airflow\.cfg|tsconfig[^/]*\.json|vite\.config\.[jt]s|next\.config\.[jm]?[jt]s|webpack\.config\.[jt]s)$', re.I)


@functools.lru_cache(maxsize=1)
def linguist_lists():
    """Linguist vendor.yml·documentation.yml(MIT). 우리 목적에 안 맞는 패턴은 뺀다:
    vendor의 '(^|/)\\.github/'(워크플로가 필요함)·'(^|/)cache/'(캐시 코드 폴더), documentation의 examples·demos(코드일 수 있음)."""
    base = os.path.dirname(LINGUIST)

    def load(name, drop):
        pats = []
        try:
            for line in open(os.path.join(base, name), encoding='utf-8'):
                s = line.strip()
                if not s.startswith('- '):
                    continue
                p = s[2:].strip()
                if p[:1] in ("'", '"'):
                    p = p[1:-1]
                if p in drop:
                    continue
                try:
                    pats.append(re.compile(p))
                except re.error:
                    pass
        except OSError:
            pass
        return pats
    return (load('vendor.yml', {r'(^|/)\.github/', r'(^|/)cache/'}),
            load('documentation.yml', {r'^[Ee]xamples/', r'^[Dd]emos?/'}))


TEMPLATE_EXT = ('.ejs', '.jade', '.pug', '.hbs', '.handlebars', '.mustache', '.njk', '.twig', '.erb', '.jsp', '.liquid', '.blade.php')


def classify(path):
    """-> dict(lang, ltype, kind). kind: vendor·generated·test·doc·migration·config·notebook·code·data·other"""
    by_ext, by_name = linguist()
    base = path.rsplit('/', 1)[-1]
    ext = ('.' + base.rsplit('.', 1)[-1].lower()) if '.' in base else ''
    lang, ltype = by_name.get(base) or by_ext.get(ext) or (None, None)
    if base.startswith('Dockerfile'):
        lang, ltype = 'Dockerfile', 'programming'
    if ext == '.kts' and base.endswith('.gradle.kts'):
        lang, ltype = 'Gradle', 'data'
    lv, ld = linguist_lists()
    if VENDOR.search(path) or any(p.search(path) for p in lv):
        kind = 'vendor'
    elif GENERATED.search(path):
        kind = 'generated'
    elif TEST.search(path):
        kind = 'test'
    elif MIGRATION.search(path):
        kind = 'migration'
    elif ext == '.ipynb':
        kind = 'notebook'
    elif CONFIG_NAME.search(path):
        kind = 'config'
    elif DOC.search(path) or ltype == 'prose' or any(p.search(path) for p in ld):
        kind = 'doc'
    elif ltype == 'programming' or lang in ('Vue', 'Svelte', 'HTML', 'CSS', 'SCSS', 'Sass', 'Less', 'SQL', 'Prisma', 'GraphQL') or ext in TEMPLATE_EXT:
        kind = 'code'
    elif ltype == 'data':
        kind = 'data'
    else:
        kind = 'other'
    prog_lang = lang if (ltype == 'programming' and lang not in NOT_A_LANGUAGE and kind in ('code', 'test')) else None
    return dict(lang=lang, ltype=ltype, kind=kind, prog_lang=prog_lang)


# ---------------- 날짜·기간·단계
def kst_date(iso):
    """'2025-03-01T10:00:00+09:00' -> date(KST)"""
    return datetime.datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(KST).date()


def duration_days(dates, gap=30):
    """「문서」 lv-calc 공통 규칙 6(유통기한 1달): 날짜를 순서대로 놓고 30일 넘게 비면 끊는다.
    구간마다 첫날~마지막 날을 양 끝 포함해 세고(혼자 떨어진 커밋은 1일) 모두 더한다.
    예: 1/1·1/20·2/10·6/1·6/15 → 41 + 15 = 56. 「제안」 [B-18]: 날짜 차가 31일 이상이면 끊는다."""
    ds = sorted(set(dates))
    if not ds:
        return 0
    total, start, prev = 0, ds[0], ds[0]
    for d in ds[1:]:
        if (d - prev).days > gap:
            total += (prev - start).days + 1
            start = d
        prev = d
    return total + (prev - start).days + 1


def stage(value, starts):
    """「문서」 공통 규칙 1: 그 단계 시작값 이상이면 그 단계(0~5). starts = [1단계, …, 5단계 시작값]"""
    if value is None or starts is None:
        return None
    st = 0
    for i, s in enumerate(starts, 1):
        if value >= s:
            st = i
    return st


# ---------------- 사람·레포
class Repo:
    def __init__(self, pid, meta):
        self.pid = pid
        self.meta = meta
        self.key = meta['key']
        self.full_name = meta['full_name']
        self.dir = meta['dir']
        self.refs = meta['refs']                       # [{'name': 'main', 'ref': 'refs/remotes/origin/main', 'sha': ...}]
        self.commits = meta['commits']                 # 분석 브랜치의 머지 아닌 커밋(모든 작성자). own=True가 내 커밋
        self.files = meta['files']                     # 분석 브랜치 끝의 파일(기본 브랜치 우선): path, sha, size, ref, lang, kind, prog_lang, my_lines, lines
        self.prs = meta.get('prs', [])
        self.own_share = meta.get('own_share')

    @property
    def own_commits(self):
        return [c for c in self.commits if c['own']]

    def text(self, path, ref=None, maxsize=1_500_000):
        """파일 내용(없거나 크면 None). ref가 없으면 색인한 판(그 파일이 있던 분석 브랜치 끝)."""
        f = self.file(path)
        sha = f['sha'] if (f and ref is None) else None
        spec = sha if sha else f'{ref or self.refs[0]["ref"]}:{path}'
        return _cat(self.dir, spec, maxsize)

    def file(self, path):
        return self._files_by_path().get(path)

    @functools.lru_cache(maxsize=None)
    def _files_by_path(self):
        return {f['path']: f for f in self.files}

    def own_line_set(self, path):
        """지금 남은 내 줄 번호(1부터). blame을 안 한 파일이면 None."""
        f = self.file(path)
        if not f or f.get('my_ranges') is None:
            return None
        s = set()
        for a, b in f['my_ranges']:
            s.update(range(a, b + 1))
        return s

    def show(self, sha, paths=(), maxbytes=400_000):
        """커밋 메시지와 diff(크기 상한)."""
        rc, out = git(self.dir, 'show', '--format=%B', '--no-color', sha, '--', *paths, timeout=120)
        return out[:maxbytes].decode('utf-8', errors='replace') if rc == 0 else None


@functools.lru_cache(maxsize=20000)
def _cat(d, spec, maxsize):
    rc, out = git(d, 'cat-file', '-s', spec, timeout=60)
    if rc != 0:
        return None
    try:
        if int(out.strip() or 0) > maxsize:
            return None
    except ValueError:
        return None
    rc, out = git(d, 'cat-file', '-p', spec, timeout=60)
    return out.decode('utf-8', errors='replace') if rc == 0 else None


class Person:
    def __init__(self, pid):
        self.pid = pid
        self.meta = json.load(open(os.path.join(INDEX, pid, 'person.json')))
        self.login = self.meta['login']
        self.role, self.level = self.meta['role'], self.meta['level']
        self.repos = []
        for k in self.meta['repo_keys']:
            p = os.path.join(INDEX, pid, k + '.json')
            if os.path.exists(p):
                self.repos.append(Repo(pid, json.load(open(p))))


def people():
    return json.load(open(os.path.join(S2, 'people.json')))


def load_person(pid):
    return Person(pid)


def evidence(repo, path=None, line=None, sha=None, rule=None, note=None, end=None):
    """근거 기록(위치만, 코드 내용은 넣지 않는다)."""
    e = dict(repo=repo.key, rule=rule)
    if path:
        e['path'] = path
    if line:
        e['line'] = line
    if end:
        e['end'] = end
    if sha:
        e['sha'] = sha
    if note:
        e['note'] = note[:200]
    return e


def write_vars(pid, cat, data):
    d = os.path.join(OUT, pid)
    os.makedirs(d, exist_ok=True)
    json.dump(data, open(os.path.join(d, f'vars-{cat}.json'), 'w'), ensure_ascii=False, indent=1)
