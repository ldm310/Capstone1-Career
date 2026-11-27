#!/usr/bin/env python3
"""백엔드 게이트(「문서」 백엔드 v5 규칙 1, 부록 A-2.1). 버림용 스파이크(2026-11-26, 제품 코드 아님).

gate(person) -> {repo_key: {pass, framework, my_backend_lines, evidence, ...}}
- 서버 프레임워크로 만든 API 1개 이상이 DB까지 이어짐 + 내 백엔드 코드 50줄 이상(빈 줄·주석·생성 파일 제외).
- (레포, 프레임워크)마다 따로 판정하고 하나라도 통과하면 백엔드 레포다(부록 A-2.1 「제안」).
- 규칙 스택: Spring Boot · NestJS · Express · Django(DRF) · FastAPI. 그 밖의 서버 프레임워크는 모름(규칙 없음) + S5 대상.
- 파서: Python은 표준 ast(옛 owncheck_v2 index_py), Java·Kotlin·JS·TS는 주석·문자열을 가린 정규식(옛 owncheck_v2).
  tree-sitter는 이 스파이크 환경에 없다(설치하지 않음). 결과의 parser 칸에 남긴다.
- 받은 레포는 읽기만 한다(git cat-file). 실행·빌드·설치하지 않는다. 결과에는 위치만 남긴다.

다른 모듈이 쓰는 것: gate(person), context(repo)(oc Repo·라우트·백엔드 파일·글), my_lines_in(repo, path, start, end).
"""
import functools
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.setrecursionlimit(10000)
import s2lib as L  # noqa: E402
import cat_backend_a_oc as oc  # noqa: E402

PARSER = {'py': 'python-ast(owncheck_v2.index_py)', 'java': 'regex-masked(owncheck_v2.index_java)', 'ts': 'regex-masked(owncheck_v2.index_ts)'}
RULE_FW = ('spring', 'nest', 'express', 'django', 'fastapi')
FW_LANG = {'spring': ('.java', '.kt'), 'nest': ('.ts', '.js', '.mjs', '.cjs'), 'express': ('.ts', '.js', '.mjs', '.cjs'),
           'django': ('.py',), 'fastapi': ('.py',)}
FW_NAME = {'spring': 'Spring Boot', 'nest': 'NestJS', 'express': 'Express', 'django': 'Django', 'fastapi': 'FastAPI'}
NODE_BUILD = ('package.json',)
JVM_BUILD = ('build.gradle', 'build.gradle.kts', 'pom.xml')
PY_BUILD = ('requirements.txt', 'requirements-dev.txt', 'requirements_dev.txt', 'pyproject.toml', 'Pipfile', 'setup.py', 'manage.py')
OTHER_BUILD = {'go.mod': 'go', 'Gemfile': 'ruby', 'composer.json': 'php'}
FRONT_PATH = re.compile(r'(^|/)(frontend|front|client|web|fe|mobile|android|ios|components|pages(?!/api)|hooks|store|views|public|static|assets)(/|$)', re.I)
MAX_READ = 600_000


# ---------------- 읽기(색인 판, cat-file --batch)
def batch_read(repo, paths, maxsize=MAX_READ):
    """{path: text}. 크거나 부분 clone에서 빠진 파일은 None."""
    want = []
    for p in paths:
        f = repo.file(p)
        if f and f.get('sha') and (f.get('size') or 0) <= maxsize:
            want.append((f['sha'], p))
    out = {p: None for p in paths}
    if not want:
        return out
    pr = subprocess.run(['git', '-C', repo.dir, '-c', 'core.hooksPath=/dev/null', 'cat-file', '--batch'],
                        input=('\n'.join(s for s, _ in want) + '\n').encode(), capture_output=True, env=L.GENV, timeout=600)
    data, i, k = pr.stdout, 0, 0
    while i < len(data) and k < len(want):
        nl = data.find(b'\n', i)
        if nl < 0:
            break
        h = data[i:nl].decode(errors='replace').split()
        sha, path = want[k]
        k += 1
        if len(h) < 3 or h[1] != 'blob':
            i = nl + 1
            continue
        size = int(h[2])
        st = nl + 1
        out[path] = data[st:st + size].decode('utf-8', errors='replace')
        i = st + size + 1
    return out


def ext_of(p):
    b = p.rsplit('/', 1)[-1]
    return ('.' + b.rsplit('.', 1)[-1].lower()) if '.' in b else ''


def dirname(p):
    return p.rsplit('/', 1)[0] if '/' in p else ''


def under(path, root):
    return root == '' or path == root or path.startswith(root + '/')


# ---------------- 프레임워크(빌드 파일 + import)
def fw_from_build(name, text):
    """-> (규칙 프레임워크 set, 규칙 없는 서버 프레임워크 set, 뜻 없는 표시)"""
    fw, other = set(), set()
    t = text or ''
    if name == 'package.json':
        try:
            j = json.loads(t)
            deps = set((j.get('dependencies') or {}).keys()) | set((j.get('devDependencies') or {}).keys())
        except Exception:
            deps = set(re.findall(r'"(@?[\w./-]+)"\s*:', t))
        if '@nestjs/core' in deps:
            fw.add('nest')
        elif 'express' in deps:
            fw.add('express')
        for d, nm in (('fastify', 'Fastify'), ('koa', 'Koa'), ('hono', 'Hono'), ('elysia', 'Elysia'), ('@hapi/hapi', 'hapi'),
                      ('restify', 'restify'), ('@adonisjs/core', 'AdonisJS'), ('apollo-server', 'Apollo Server'), ('@apollo/server', 'Apollo Server'),
                      ('@trpc/server', 'tRPC'), ('next', 'Next.js(API)'), ('@sveltejs/kit', 'SvelteKit'), ('nuxt', 'Nuxt(server)')):
            if d in deps and not fw:
                other.add(nm)
    elif name in JVM_BUILD:
        if re.search(r'spring-boot', t):
            fw.add('spring')
        elif re.search(r'springframework', t):
            other.add('Spring MVC(Boot 아님)')
        for pat, nm in ((r'io\.ktor', 'Ktor'), (r'micronaut', 'Micronaut'), (r'quarkus', 'Quarkus'), (r'javalin', 'Javalin'), (r'sparkjava', 'Spark Java')):
            if re.search(pat, t) and not fw:
                other.add(nm)
    elif name in PY_BUILD and name != 'manage.py':
        low = t.lower()
        if re.search(r'(^|[\s"\'\[,])django([<>=~!\s"\',;\]]|$)', low, re.M) or 'djangorestframework' in low:
            fw.add('django')
        if re.search(r'(^|[\s"\'\[,])fastapi', low, re.M):
            fw.add('fastapi')
        for pat, nm in ((r'(^|[\s"\'\[,])flask', 'Flask'), (r'(^|[\s"\'\[,])tornado', 'Tornado'), (r'(^|[\s"\'\[,])sanic', 'Sanic'),
                        (r'(^|[\s"\'\[,])aiohttp', 'aiohttp'), (r'(^|[\s"\'\[,])bottle', 'Bottle'), (r'(^|[\s"\'\[,])falcon', 'Falcon')):
            if re.search(pat, low, re.M) and not fw:
                other.add(nm)
    return fw, other


IMPORT_FW = [
    ('.py', 'django', re.compile(r'^\s*(?:from|import)\s+(?:django|rest_framework)\b', re.M)),
    ('.py', 'fastapi', re.compile(r'^\s*(?:from|import)\s+fastapi\b', re.M)),
    ('.py', 'Flask', re.compile(r'^\s*(?:from|import)\s+flask\b', re.M)),
    ('.js', 'nest', re.compile(r'[\'"]@nestjs/(?:common|core)[\'"]')),
    ('.js', 'express', re.compile(r'require\(\s*[\'"]express[\'"]\s*\)|from\s+[\'"]express[\'"]')),
    ('.js', 'Fastify', re.compile(r'require\(\s*[\'"]fastify[\'"]\s*\)|from\s+[\'"]fastify[\'"]')),
    ('.js', 'Koa', re.compile(r'require\(\s*[\'"]koa[\'"]\s*\)|from\s+[\'"]koa[\'"]')),
    ('.java', 'spring', re.compile(r'^\s*import\s+org\.springframework\.web\.bind\.annotation\b', re.M)),
]


def lang_group(path):
    e = ext_of(path)
    if e == '.py':
        return '.py'
    if e in ('.js', '.ts', '.mjs', '.cjs'):
        return '.js'
    if e in ('.java', '.kt'):
        return '.java'
    return None


# ---------------- DB 접근(부록 A-2.1: API → DB 호출 경로. 메모리 자료 구조는 DB가 아니다)
JAVA_DB = re.compile(r'\b(?:jdbcTemplate|namedParameterJdbcTemplate|jdbc|entityManager|em|mongoTemplate|reactiveMongoTemplate|sqlSession|sqlSessionTemplate|'
                     r'jpaQueryFactory|queryFactory|dslContext|dsl|r2dbcEntityTemplate|databaseClient)\s*\.\s*\w+\s*\(|\bDriverManager\s*\.\s*getConnection\s*\(|'
                     r'\.(?:prepareStatement|executeQuery|executeUpdate)\s*\(')
TS_DB = re.compile(r'\bprisma\s*\.\s*\w+\s*\.\s*(?:find\w*|create\w*|update\w*|delete\w*|upsert|count|aggregate|groupBy)\s*\(|\bprisma\s*\.\s*\$(?:queryRaw|executeRaw|transaction)\w*|'
                   r'\bgetRepository\s*\(|\bgetManager\s*\(|\.createQueryBuilder\s*\(|\bdataSource\s*\.\s*(?:getRepository|query|manager|transaction)\b|'
                   r'\b(?:knex|db|pool|connection|conn|client|sequelize|sql|database|mysql|pg|dbPool|promisePool)\s*\.\s*(?:query|execute|raw|select|insert|update|delete|from|collection|transaction|insertInto|selectFrom|deleteFrom|updateTable)\s*\(|'
                   r'\.collection\s*\(\s*[\'"`]|'
                   r'\b[A-Z]\w*\s*\.\s*(?:find|findOne|findById|findAll|findByPk|findAndCountAll|findOrCreate|create|insertMany|updateOne|updateMany|deleteOne|deleteMany|'
                   r'findByIdAndUpdate|findByIdAndDelete|findByIdAndRemove|findOneAndUpdate|findOneAndDelete|aggregate|countDocuments|bulkCreate|destroy|upsert|exists)\s*\(|'
                   r'\bthis\s*\.\s*\w*(?:[Rr]epository|[Rr]epo|[Mm]odel|prisma|Prisma|em|entityManager|dataSource|knex|db)\s*\.\s*\w+\s*[(.]|'
                   r'\bnew\s+[A-Z]\w*\s*\([^)]*\)\s*\.\s*save\s*\(|\b\w+\s*\.\s*save\s*\(|\.(?:populate|exec|lean)\s*\(|\bdrizzle\b|\bdb\s*\.\s*(?:select|insert|update|delete)\s*\(')
PY_DB = re.compile(r'\.objects\s*\.|\bget_object_or_404\s*\(|\bget_list_or_404\s*\(|\.save\s*\(|\.delete\s*\(\s*\)|'
                   r'\b(?:db|session|Session|db_session|async_session|dbsession|sess|database)\s*\.\s*(?:query|add|add_all|commit|execute|delete|get|merge|scalars?|exec|refresh|flush|fetch_all|fetch_one|fetch_val)\s*\(|'
                   r'\bcursor\s*\(\s*\)|\bcursor\s*\.\s*execute\w*\s*\(|\.(?:insert_one|insert_many|find_one|update_one|update_many|delete_one|delete_many|aggregate|count_documents|bulk_write)\s*\(|'
                   r'\.find\s*\(\s*\{|\bconn\w*\s*\.\s*execute\s*\(|\bawait\s+[A-Z]\w*\s*\.\s*(?:create|filter|get|all|get_or_none)\s*\(|\.raw\s*\(')
PY_DB_CLASS_ASSIGN = ('queryset', 'model', 'Meta.model')
SQL_CALL = re.compile(r'\.\s*(?:query|execute|raw|executeQuery|executeUpdate)\s*\(\s*(?:sql\w*|query\w*|q|stmt|statement|[`\'"]\s*(?:select|insert|update|delete|with)\b)', re.I)


def db_hit(repo, f):
    """함수 f 안의 DB 접근 줄(함수 기준 1부터) 또는 None."""
    lang = f['lang']
    m = f.get('masked') or f.get('code') or ''
    rx = JAVA_DB if lang == 'java' else TS_DB if lang == 'ts' else PY_DB
    mo = rx.search(m)
    if mo:
        return oc.line_of(m, mo.start()), 'pattern'
    c = f.get('code') or ''
    mo = SQL_CALL.search(c)
    if mo:
        return oc.line_of(c, mo.start()), 'sql-call'
    if lang == 'java':
        for recv, name, this, args, cline in oc.calls_of(f):
            if not recv or recv == 'this':
                continue
            if re.match(r'(?i)^\w*(?:dao|repository|repo|sqlSession)$', recv) and not repo.resolve_call(f, recv, name, this):
                return cline or 1, 'dao-name'
            t = repo.var_type(f, recv) if recv[0].islower() else recv
            bt = repo.base_type(t) if t else None
            if not bt:
                continue
            if bt in repo.repo_entity:
                return cline or 1, 'spring-data-repository'
            for cls in repo.classes.get(bt, []):
                if cls.get('lang') == 'java' and cls.get('kind') == 'interface' and re.search(r'@(?:Mapper|Repository)\b', cls.get('annos') or '') \
                        and not cls['methods'].get(name, [None])[0:1] == [None] and not any(repo.has_body(g) for g in cls['methods'].get(name, [])):
                    return cline or 1, 'mapper-interface'
                if cls.get('lang') == 'java' and cls.get('kind') == 'interface' and re.search(r'@Mapper\b', cls.get('annos') or ''):
                    return cline or 1, 'mybatis-mapper'
    if lang == 'py':
        cls_list = repo.classes.get(f.get('cls') or '', [])
        for cls in cls_list:
            if cls.get('file') == f['file'] and any(k in cls.get('assigns', {}) for k in PY_DB_CLASS_ASSIGN):
                return 1, 'django-class-queryset'
    return None


def code_line(f, off):
    """함수 f의 code 안 off번째 줄(1부터) → 파일 줄. Java·TS 메서드는 code가 어노테이션부터 시작하고 f['line']은 이름 줄이다."""
    if f['lang'] in ('java', 'ts') and f.get('annos') and (f.get('code') or '').startswith(f['annos']):
        return f['line'] - f['annos'].count('\n') + off - 1
    return f['line'] + off - 1


def reaches_db(repo, handlers, depth=4, limit=60):
    """핸들러에서 호출 그래프를 따라(최대 depth) DB 접근에 닿으면 (함수, 줄, 방법)."""
    work = [(h, 0) for h in handlers]
    seen = set()
    n = 0
    while work and n < limit:
        f, d = work.pop(0)
        key = (f['file'], f.get('cls'), f['name'], f['line'])
        if key in seen:
            continue
        seen.add(key)
        n += 1
        hit = db_hit(repo, f)
        if hit:
            return f, code_line(f, hit[0]), hit[1]
        if d >= depth:
            continue
        for recv, name, this, args, cline in oc.calls_of(f):
            for g in repo.resolve_call(f, recv, name, this):
                work.append((g, d + 1))
    return None


# ---------------- Django URL → 뷰(라우트). owncheck_v2는 수정 API만 봐서 게이트용으로 더한다
DJ_URL = re.compile(r'\b(?:path|re_path|url)\s*\(\s*r?[\'"]([^\'"]*)[\'"]\s*,\s*([\w.]+)(\s*\.\s*as_view\s*\()?')
DJ_REG = re.compile(r'\brouter\s*\.\s*register\s*\(\s*r?[\'"]([^\'"]*)[\'"]\s*,\s*([\w.]+)')


def django_routes(repo):
    eps = []
    for path, (lang, code, masked) in repo.files.items():
        if lang != 'py' or not path.endswith('urls.py'):
            continue
        for rx, kind in ((DJ_URL, 'django-url'), (DJ_REG, 'drf-router')):
            for mo in rx.finditer(code):
                chain = re.sub(r'\.as_view$', '', mo.group(2))
                ref = chain.split('.')[-1]
                hs = []
                if ref[:1].isupper():
                    for cls in repo.classes.get(ref, []):
                        meths = [f for mn, fl in cls['methods'].items() for f in fl
                                 if mn in ('get', 'post', 'put', 'patch', 'delete', 'list', 'retrieve', 'create', 'update', 'partial_update', 'destroy', 'get_queryset', 'perform_create')]
                        if meths:
                            hs += meths
                        else:
                            hs.append(dict(lang='py', file=cls['file'], cls=ref, name='<class>', params=[], code=cls.get('code', ''), masked=cls.get('code', ''),
                                           line=cls['line'], annos='', node=None))
                else:
                    hs = [f for f in repo.funcs.get(ref, []) if f['lang'] == 'py' and f['cls'] is None]
                if not hs:
                    continue
                if 'include' in mo.group(2):
                    continue
                eps.append(dict(file=path, line=oc.line_of(code, mo.start()), kind=kind, verb='ANY', path=mo.group(1), name=ref, handlers=hs, guards=[], guard_names=[]))
    return eps


def route_fw(repo, ep, file_fw):
    k = ep['kind']
    if k == 'spring':
        return 'spring'
    if k == 'nest':
        code = repo.files.get(ep['file'], ('', '', ''))[1]
        if '@nestjs/' in code:
            return 'nest'
        if 'routing-controllers' in code:      # routing-controllers는 Express 위에서 돈다
            return 'express'
        return 'nest' if 'nest' in file_fw.get(ep['file'], set()) else 'other'
    if k in ('express',):
        fws = file_fw.get(ep['file'], set())
        if 'express' in fws or 'nest' in fws:
            return 'express' if 'express' in fws else 'nest'
        return 'other'
    if k in ('drf-generic', 'drf-view', 'drf-action', 'py-fview', 'django-url', 'drf-router'):
        return 'django'
    if k == 'py-deco':
        code = repo.files.get(ep['file'], ('', '', ''))[1]
        if re.search(r'^\s*(?:from|import)\s+fastapi\b', code, re.M):
            return 'fastapi'
        # 같은 패키지에서 APIRouter를 import한 경우(라우터 파일이 fastapi를 직접 import)
        fws = file_fw.get(ep['file'], set())
        return 'fastapi' if 'fastapi' in fws and not re.search(r'^\s*(?:from|import)\s+flask\b', code, re.M) else 'other'
    return 'other'


# ---------------- 파일 종류 보정(s2lib GENERATED가 'out/' 폴더를 생성물로 본다: 헥사고날 adapter/out 오탐)
GEN_NO_OUT = re.compile(L.GENERATED.pattern.replace('|out|', '|'), re.I)


def kind_of(f):
    k = f['kind']
    if k == 'generated' and re.search(r'(^|/)out/', f['path']) and not re.match(r'out/', f['path']) and not GEN_NO_OUT.search(f['path']):
        c = L.classify(f['path'].replace('/out/', '/out_/'))
        return c['kind']
    return k


_OWN = {}
SKIP_NO_OUT = re.compile(oc.SKIP.pattern.replace('|build|out|', '|build|'), re.I)


def own_set(repo, path):
    """지금 남은 내 줄. 색인이 blame하지 않은 보정 파일(kind_of로 code가 된 것)은 여기서 blame한다(읽기만)."""
    s = repo.own_line_set(path)
    if s is not None:
        return s
    f = repo.file(path)
    if not f or kind_of(f) == f['kind'] or (f.get('size') or 0) > 300_000:
        return None
    k = (repo.pid, repo.key, path)
    if k not in _OWN:
        own = {c['sha'] for c in repo.commits if c['own']}
        touched = any(x['path'] == path for c in repo.commits if c['own'] for x in c['files'])
        if not touched:
            _OWN[k] = set()
        else:
            rc, out = L.git(repo.dir, 'blame', '--porcelain', f['ref'], '--', path, timeout=300)
            mine, cur = set(), None
            if rc == 0:
                for line in out.decode('utf-8', errors='replace').splitlines():
                    m = re.match(r'^([0-9a-f]{40}) \d+ (\d+)', line)
                    if m:
                        cur = (m.group(1), int(m.group(2)))
                        continue
                    if line.startswith('\t') and cur:
                        if cur[0] in own:
                            mine.add(cur[1])
                        cur = None
                _OWN[k] = mine
            else:
                _OWN[k] = None
    return _OWN[k]


# ---------------- 내 줄
def masked_lines(path, text):
    if text is None:
        return None
    if path.endswith('.py'):
        t = oc.strip_py(text)
        # docstring·주석 줄 빼기: 줄 전체가 문자열 리터럴만인 줄은 남긴다(간단히)
    else:
        t = oc.strip_c(text)[0]
    return t.split('\n')


def my_code_lines(repo, path, text, start=None, end=None):
    """[start, end] 범위(없으면 파일 전체)에서 빈 줄·주석을 뺀 내 줄 수, 전체 줄 수. blame 없으면 (None, total)."""
    ml = masked_lines(path, text)
    if ml is None:
        return None, None
    own = own_set(repo, path)
    a = start or 1
    b = end or len(ml)
    tot = sum(1 for i in range(a, min(b, len(ml)) + 1) if ml[i - 1].strip())
    if own is None:
        return None, tot
    mine = sum(1 for i in range(a, min(b, len(ml)) + 1) if i in own and ml[i - 1].strip())
    return mine, tot


# ---------------- 레포 문맥(cat_backend_a·b가 같이 쓴다)
_CTX = {}


def context(repo):
    """레포 문맥(한 번만 만든다)."""
    k = (repo.pid, repo.key)
    if k not in _CTX:
        _CTX[k] = _build_context(repo)
    return _CTX[k]


def _build_context(repo):
    """-> dict(roots, file_fw, other_fw, texts, oc(옛 Repo), routes, backend_files{fw: [path]})"""
    files = [f for f in repo.files if kind_of(f) not in ('vendor', 'generated')]
    names = {}
    for f in files:
        b = f['path'].rsplit('/', 1)[-1]
        if b in NODE_BUILD + JVM_BUILD + PY_BUILD or b in OTHER_BUILD or b.endswith('.csproj'):
            names[f['path']] = b
    btxt = batch_read(repo, list(names))
    roots = []          # (dir, family, fw set, other set, build path)
    for p, b in names.items():
        fam = 'node' if b in NODE_BUILD else 'jvm' if b in JVM_BUILD else 'py' if b in PY_BUILD else 'other'
        if fam == 'other':
            nm = 'ASP.NET' if b.endswith('.csproj') else OTHER_BUILD[b]
            t = btxt.get(p) or ''
            if b == 'go.mod':
                m = re.search(r'github\.com/(gin-gonic/gin|labstack/echo|gofiber/fiber|go-chi/chi|gorilla/mux)', t)
                nm = 'Go ' + m.group(1).split('/')[-1] if m else None
            elif b == 'Gemfile':
                nm = 'Rails' if re.search(r'[\'"]rails[\'"]', t) else ('Sinatra' if 'sinatra' in t else None)
            elif b == 'composer.json':
                nm = 'Laravel' if 'laravel/framework' in t else ('Symfony' if 'symfony/' in t else None)
            elif b.endswith('.csproj'):
                nm = 'ASP.NET' if re.search(r'Microsoft\.AspNetCore|Microsoft\.NET\.Sdk\.Web|System\.Web\.Mvc', t) else None
            roots.append((dirname(p), 'other', set(), {nm} if nm else set(), p))
            continue
        fw, other = fw_from_build(b, btxt.get(p))
        if b == 'manage.py' and re.search(r'django', btxt.get(p) or ''):
            fw.add('django')
        roots.append((dirname(p), fam, fw, other, p))
    # 코드 파일 → 가장 가까운 같은 계열 루트
    code = [f for f in files if kind_of(f) == 'code' and lang_group(f['path'])]
    fam_of = {'.py': 'py', '.js': 'node', '.java': 'jvm'}
    file_fw, file_root = {}, {}
    for f in code:
        fam = fam_of[lang_group(f['path'])]
        best = None
        for r in roots:
            if r[1] == fam and under(f['path'], r[0]) and (best is None or len(r[0]) > len(best[0])):
                best = r
        file_root[f['path']] = best
        file_fw[f['path']] = set(best[2]) if best else set()
    # import로 보충(빌드 파일이 없거나 빠진 경우). 읽기는 한 번에
    texts = batch_read(repo, [f['path'] for f in code])
    other_fw = set()
    for r in roots:
        other_fw |= r[3]
    for f in code:
        t = texts.get(f['path'])
        if t is None:
            continue
        g = lang_group(f['path'])
        for lg, nm, rx in IMPORT_FW:
            if lg == g and rx.search(t):
                if nm in RULE_FW:
                    if nm == 'spring' and not any('spring' in r[2] for r in roots if r[1] == 'jvm'):
                        other_fw.add('Spring MVC(Boot 아님)')
                        continue
                    file_fw[f['path']].add(nm)
                else:
                    other_fw.add(nm)
    # 백엔드 후보 파일: 규칙 프레임워크 루트 아래 + 그 프레임워크 언어
    bfiles = {fw: [] for fw in RULE_FW}
    rule_roots = [r for r in roots if r[2]]
    for f in code:
        p = f['path']
        fws = file_fw.get(p) or set()
        if not fws:
            # 같은 계열의 규칙 루트 아래면 그 루트의 프레임워크
            continue
        for fw in fws:
            if ext_of(p) not in FW_LANG[fw]:
                continue
            if fw in ('nest', 'express') and FRONT_PATH.search(p) and not re.search(r'(^|/)(server|api|backend|src/main)(/|$)', p, re.I):
                continue
            bfiles[fw].append(p)
    # 옛 owncheck_v2 색인(백엔드 후보 파일 + MyBatis XML·Prisma)
    want = sorted({p for v in bfiles.values() for p in v})
    extra = [f['path'] for f in files if f['path'].endswith(('.prisma',)) or (f['path'].endswith('.xml') and 'mapper' in f['path'].lower())]
    xt = batch_read(repo, extra)
    raw = {p: texts[p] for p in want if texts.get(p) is not None and not SKIP_NO_OUT.search(p)}
    for p, t in xt.items():
        if t and (not p.endswith('.xml') or '<mapper' in t):
            raw[p] = t
    unreadable = [p for p in want if texts.get(p) is None]
    oc.blobs = lambda d, _r=raw: _r
    ocr = oc.Repo(repo.key, repo.dir)
    eps = []
    try:
        eps = oc.routes(ocr, keep_all=True)
    except RecursionError:
        pass
    eps += django_routes(ocr)
    for e in eps:
        e['fw'] = route_fw(ocr, e, file_fw)
    return dict(roots=[dict(dir=r[0], family=r[1], fw=sorted(r[2]), other=sorted(r[3]), build=r[4]) for r in roots],
                file_fw={k: sorted(v) for k, v in file_fw.items() if v}, other_fw=sorted(x for x in other_fw if x), texts=texts, oc=ocr,
                routes=eps, backend_files=bfiles, unreadable=unreadable, build_texts=btxt)


def ep_lines(ep):
    """라우트(핸들러) 줄 범위: (path, start, end)"""
    h = ep['handlers'][0] if ep['handlers'] else None
    if not h:
        return ep['file'], ep['line'], ep['line']
    n = (h.get('code') or '').count('\n')
    return h['file'], h['line'], h['line'] + n


def is_my_api(repo, ctx, ep):
    """「제안」 [B-43]: 라우트 정의와 핸들러 본문의 줄(빈 줄·주석 뺌) 중 내 줄이 과반이면 내 API."""
    path, a, b = ep_lines(ep)
    t = ctx['texts'].get(path)
    if t is None:
        return None
    mine, tot = my_code_lines(repo, path, t, a, b)
    if mine is None:
        return None
    if ep['file'] != path:
        m2, t2 = my_code_lines(repo, ep['file'], ctx['texts'].get(ep['file']), ep['line'], ep['line'])
        if m2 is not None:
            mine, tot = mine + m2, tot + t2
    return tot > 0 and mine * 2 > tot


# ---------------- 게이트
def gate_repo(repo):
    ctx = context(repo)
    res = dict(pass_=False, frameworks={}, other_fw=ctx['other_fw'], my_backend_lines=0, evidence=[], fail_reason=None,
               state='value_rule', parser=PARSER, unreadable=len(ctx['unreadable']))
    best = None
    for fw in RULE_FW:
        bf = ctx['backend_files'][fw]
        eps = [e for e in ctx['routes'] if e.get('fw') == fw]
        if not bf and not eps:
            continue
        mine = mine_all = 0
        blame_missing = 0
        for p in bf:
            m, t = my_code_lines(repo, p, ctx['texts'].get(p))
            if m is None:
                if t:
                    blame_missing += 1
                continue
            mine += m
        # [B-44] 대안: 테스트·설정 파일 줄도 넣기
        roots = [r['dir'] for r in ctx['roots'] if fw in r['fw']] or ['']
        tc = [f['path'] for f in repo.files if f['kind'] in ('test', 'config') and any(under(f['path'], d) for d in roots)
              and (ext_of(f['path']) in FW_LANG[fw] or f['kind'] == 'config')]
        tct = batch_read(repo, tc)
        for p in tc:
            m, t = my_code_lines(repo, p, tct.get(p))
            mine_all += m or 0
        mine_all += mine
        db_any = db_mine = None
        n_my = 0
        for e in eps:
            my = is_my_api(repo, ctx, e)
            if my:
                n_my += 1
            if db_any and (db_mine or not my):
                continue
            hit = reaches_db(ctx['oc'], e['handlers'])
            if hit:
                g, ln, how = hit
                ev = dict(route=L.evidence(repo, path=e['file'], line=e['line'], rule=f'backend.gate.{fw}.route-db@1', note=f'{e["verb"]} {e["path"][:60]}'),
                          db=L.evidence(repo, path=g['file'], line=ln, rule=f'backend.gate.{fw}.db-{how}@1'))
                if not db_any:
                    db_any = ev
                if my and not db_mine:
                    db_mine = ev
        ok_any = bool(eps) and bool(db_any) and mine >= 50
        ok_mine = bool(eps) and bool(db_mine) and mine >= 50
        reason = None
        if not eps:
            reason = 'API 없음'
        elif not db_any:
            reason = 'DB까지 안 이어짐'
        elif mine < 50:
            reason = '50줄 미만'
        rec = dict(pass_=ok_any, pass_my_api=ok_mine, routes=len(eps), my_routes=n_my, my_backend_lines=mine, my_lines_with_test_config=mine_all,
                   backend_files=len(bf), blame_missing=blame_missing, fail_reason=reason, db_evidence=db_any, db_evidence_my_api=db_mine,
                   pass_with_test_config=bool(eps) and bool(db_any) and mine_all >= 50)
        res['frameworks'][fw] = rec
        if ok_any and (best is None or mine > res['frameworks'][best]['my_backend_lines']):
            best = fw
    if best:
        r = res['frameworks'][best]
        res.update(pass_=True, framework=best, my_backend_lines=r['my_backend_lines'], evidence=[r['db_evidence']['route'], r['db_evidence']['db']])
    else:
        res['framework'] = None
        if res['frameworks']:
            fwb = max(res['frameworks'], key=lambda k: res['frameworks'][k]['my_backend_lines'])
            res['my_backend_lines'] = res['frameworks'][fwb]['my_backend_lines']
            res['fail_reason'] = res['frameworks'][fwb]['fail_reason']
        elif ctx['other_fw']:
            res['fail_reason'] = '규칙 없는 스택: ' + ', '.join(ctx['other_fw'])
            res['state'] = 'unknown_no_rule'
        else:
            res['fail_reason'] = '서버 프레임워크 없음'
            res['state'] = 'zero_unused'
    # 규칙 없는 스택 코드가 같이 있으면 표시(S5 대상 재료)
    res['other_stack_my_lines'] = 0
    if ctx['other_fw']:
        n = 0
        for f in repo.files:
            if f['kind'] == 'code' and lang_group(f['path']) and not any(f['path'] in v for v in ctx['backend_files'].values()):
                n += f.get('my_lines') or 0
        res['other_stack_my_lines'] = n
    res['pass'] = res.pop('pass_')
    for v in res['frameworks'].values():
        v['pass'] = v.pop('pass_')
    return res


def gate(person):
    """-> {repo_key: {pass, framework, my_backend_lines, evidence, frameworks, fail_reason, state, ...}}"""
    out = {}
    for r in person.repos:
        if r.meta.get('error') or not r.own_commits:
            out[r.key] = dict(**{'pass': False}, framework=None, my_backend_lines=0, evidence=[], frameworks={}, other_fw=[],
                              fail_reason='레포 받기 실패' if r.meta.get('error') else '내 커밋 없음',
                              state='unknown_failed' if r.meta.get('error') else 'zero_unused')
            continue
        try:
            out[r.key] = gate_repo(r)
        except Exception as e:  # 레포 하나가 실패해도 계속
            out[r.key] = dict(**{'pass': False}, framework=None, my_backend_lines=0, evidence=[], frameworks={}, other_fw=[],
                              fail_reason='분석 실패: ' + repr(e)[:120], state='unknown_failed')
    return out


if __name__ == '__main__':
    import time
    for pid in sys.argv[1:]:
        t = time.time()
        P = L.load_person(pid)
        g = gate(P)
        for k, v in g.items():
            if v['pass'] or v.get('frameworks') or v.get('other_fw'):
                print(pid, k.split('__', 1)[-1][:28], 'PASS' if v['pass'] else '----', v.get('framework'), v['my_backend_lines'], v.get('fail_reason'),
                      {fw: (x['routes'], x['my_routes'], x['my_backend_lines'], bool(x['db_evidence'])) for fw, x in v.get('frameworks', {}).items()}, v.get('other_fw'))
        print(pid, '끝', round(time.time() - t, 1), 's', file=sys.stderr)
