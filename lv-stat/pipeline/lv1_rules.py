#!/usr/bin/env python3
"""LV1 '사용' 판정 프로토타입 (git 저장소 하나를 받아 (개발자, 기술)별 판정).

old_rule : 설정 문서 4번 그대로. 내 줄의 import / 내 커밋이 추가한 의존성 줄 / 내 커밋이 바꾼 설정 파일 중
           하나라도 있으면 LV1.
new_rule : 고친 규칙.
  충족  - 내 줄에서 그 기술을 실제로 사용(import한 이름·그 이름으로 만든 변수를 호출·어노테이션·타입으로 씀)
        - 내가 쓴 앱 설정·코드의 DB 주소(jdbc:mysql, postgresql:// ...)
        - 내가 쓴 실행형 설정(Dockerfile, compose, workflow) 3줄 이상 / 참조형 설정(nginx)은 다른 설정이 참조할 때
        - 앱 설정 키(redis, kafka)는 그 기술을 코드에서 실제로 쓸 때
        - 언어: 그 언어 파일의 내 줄 5줄 이상 / API: 내 줄의 엔드포인트 정의
  정황  - 의존성을 처음 추가함(이름 기준, 버전만 바뀐 건 무시) / import 줄만 있음 / 연결 안 된 설정
  제외  - 생성기로 만든 첫 커밋(Spring Initializr, create-react-app 등)과 봇 커밋의 줄·의존성은 누구의 근거도 아님
모든 읽기는 HEAD 기준(--no-checkout 클론에서도 동작).  Usage: python3 lv1_rules.py <repo>
"""
import collections, json, os, re, subprocess, sys

# ---------------------------------------------------------------- dictionaries (공고 키워드 이름으로)
JAVA = [('org.springframework.data.jpa', ('JPA', 'Spring')), ('org.springframework.data.redis', ('Redis', 'Spring')),
        ('org.springframework.security', ('Spring Security', 'Spring')), ('org.springframework.kafka', ('Kafka', 'Spring')),
        ('org.springframework', ('Spring',)), ('jakarta.persistence', ('JPA',)), ('javax.persistence', ('JPA',)),
        ('lombok', ('Lombok',))]
NPM = {'express': ('Express',), 'mysql2': ('MySQL',), 'mysql': ('MySQL',), 'ioredis': ('Redis',), 'redis': ('Redis',),
       'react': ('React',), 'react-dom': ('React',), 'axios': ('Axios',), 'socket.io-client': ('Socket.IO',)}
PYPI = {'fastapi': ('FastAPI',), 'sqlalchemy': ('SQLAlchemy',), 'psycopg2': ('PostgreSQL',), 'psycopg2-binary': ('PostgreSQL',),
        'redis': ('Redis',), 'pydantic': ('Pydantic',), 'pydantic-core': ('Pydantic',), 'pytest': ('pytest',)}
GRADLE = {'spring-boot-starter-web': ('Spring',), 'spring-boot-starter-data-jpa': ('JPA', 'Spring'),
          'spring-boot-starter-data-redis': ('Redis', 'Spring'), 'spring-boot-starter-security': ('Spring Security', 'Spring'),
          'spring-boot-starter-validation': ('Spring',), 'lombok': ('Lombok',), 'mysql-connector-j': ('MySQL',),
          'spring-kafka': ('Kafka', 'Spring'), 'org.springframework.boot': ('Spring',)}
LANG = {'.java': 'Java', '.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript', '.ts': 'TypeScript', '.tsx': 'TypeScript'}
DBURL = [(re.compile(r'jdbc:mysql:|mysql://'), 'MySQL'), (re.compile(r'jdbc:postgresql:|postgres(?:ql)?(?:\+\w+)?://'), 'PostgreSQL')]
API = re.compile(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\b|\b(app|router)\.(get|post|put|delete|patch)\(')
EXCL = re.compile(r'(^|/)(node_modules|vendor|third_party|dist|build|fixtures|golden)/|\.min\.js$|'
                  r'(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|uv\.lock)$')
SCAFFOLD = [(r'(^|/)HELP\.md$', r'Reference Documentation'),          # Spring Initializr
            (r'(^|/)README\.md$', r'Create React App'),                # create-react-app
            (r'(^|/)src/reportWebVitals\.(ts|js)$', r''),              # create-react-app
            (r'(^|/)nest-cli\.json$', r''),                            # Nest CLI
            (r'(^|/)manage\.py$', r"Django's command-line utility")]   # django-admin startproject


def git(repo, *a):
    return subprocess.run(['git', *a], cwd=repo, capture_output=True, text=True, check=True).stdout


def kind(path):
    b, low = os.path.basename(path), path.lower()
    if EXCL.search(path): return None, ()
    if b == 'Dockerfile' or b.endswith('.Dockerfile'): return 'infra', ('Docker',)
    if re.fullmatch(r'(docker-)?compose(\.\w+)?\.ya?ml', b): return 'infra', ('Compose', 'Docker')
    if low.startswith('.github/workflows/') and low.endswith(('.yml', '.yaml')): return 'infra', ('GitHub Actions',)
    if 'nginx' in low and low.endswith('.conf'): return 'infra_ref', ('Nginx',)
    if re.fullmatch(r'application(-\w+)?\.(ya?ml|properties)', b) or b == '.env.example': return 'appcfg', ()
    if b in ('build.gradle', 'build.gradle.kts', 'package.json', 'requirements.txt'): return 'manifest', ()
    ext = os.path.splitext(b)[1]
    return ('code', (LANG[ext],)) if ext in LANG else (None, ())


def java_tech(mod):
    for pre, t in JAVA:
        if mod == pre or mod.startswith(pre + '.'): return t
    return ()


def js_tech(mod):
    if mod.startswith('.'): return ()
    root = '/'.join(mod.split('/')[:2]) if mod.startswith('@') else mod.split('/')[0]
    return NPM.get(root, ())


def py_tech(mod):
    return PYPI.get(mod.split('.')[0].lower(), ())


# ---------------------------------------------------------------- manifests
def dep_names(path, text):
    """package name -> raw line, at one revision"""
    b, out = os.path.basename(path), {}
    if b.startswith('build.gradle'):
        for m in re.finditer(r"^\s*(?:implementation|api|compileOnly|runtimeOnly|annotationProcessor|testImplementation|testRuntimeOnly)"
                             r"\s*\(?\s*['\"]([^:'\"]+):([^:'\"]+)", text, re.M):
            out[m.group(2)] = m.group(0)
        for m in re.finditer(r"^\s*id\s*\(?\s*['\"]([^'\"]+)['\"]\)?\s+version", text, re.M):
            out[m.group(1)] = m.group(0)
    elif b == 'package.json':
        try:
            j = json.loads(text)
        except ValueError:
            return out
        for sec in ('dependencies', 'devDependencies'):
            out.update({k: sec for k in (j.get(sec) or {})})
    elif b == 'requirements.txt':
        for line in text.splitlines():
            m = re.match(r'\s*([A-Za-z0-9][A-Za-z0-9._-]*)', line)
            if m and not line.strip().startswith('#'): out[m.group(1).lower().replace('_', '-')] = line
    return out


def dep_names_line(path, line):
    return dep_names(path, line) if not path.endswith('package.json') else \
        [m.group(1) for m in [re.match(r'\s*"([^"]+)"\s*:\s*"', line)] if m]


def dep_tech(path, name):
    b = os.path.basename(path)
    if b.startswith('build.gradle'): return GRADLE.get(name, ())
    if b == 'package.json': return NPM.get(name, ())
    return PYPI.get(name, ())


# ---------------------------------------------------------------- code parsing
def is_comment(ext, s):
    s = s.strip()
    return s.startswith('#') if ext == '.py' else s.startswith(('//', '/*', '*'))


def parse_imports(ext, lines):
    """line index -> [(imported name or None, techs)]"""
    out = {}
    for i, raw in enumerate(lines):
        s = raw.strip()
        if ext == '.java':
            m = re.match(r'import\s+(?:static\s+)?([\w.]+?)(\.\*)?\s*;', s)
            if m: out[i] = [(None if m.group(2) else m.group(1).rsplit('.', 1)[-1], java_tech(m.group(1)))]
        elif ext == '.py':
            m = re.match(r'import\s+([\w.]+)(?:\s+as\s+(\w+))?\s*$', s)
            if m:
                out[i] = [(m.group(2) or m.group(1).split('.')[0], py_tech(m.group(1)))]
                continue
            m = re.match(r'from\s+([\w.]+)\s+import\s+\(?([^)#]+)\)?', s)
            if m:
                out[i] = [(x.strip().split(' as ')[-1].strip(), py_tech(m.group(1))) for x in m.group(2).split(',') if x.strip()]
        elif ext in ('.js', '.jsx', '.ts', '.tsx'):
            m = re.match(r'import\s+(?:type\s+)?(.+?)\s+from\s+[\'"]([^\'"]+)[\'"]', s)
            if m:
                spec, t, names = m.group(1), js_tech(m.group(2)), []
                d = re.match(r'([\w$]+)\s*(?:,|$)', spec)
                if d: names.append(d.group(1))
                for grp in re.findall(r'\{([^}]*)\}', spec):
                    names += [x.strip().split(' as ')[-1].strip() for x in grp.split(',') if x.strip()]
                n = re.search(r'\*\s+as\s+([\w$]+)', spec)
                if n: names.append(n.group(1))
                out[i] = [(x, t) for x in names] or [(None, t)]
                continue
            m = re.match(r'import\s+[\'"]([^\'"]+)[\'"]', s)
            if m:
                out[i] = [(None, js_tech(m.group(1)))]
                continue
            m = re.match(r'(?:const|let|var)\s+(\{[^}]*\}|[\w$]+)\s*=\s*require\(\s*[\'"]([^\'"]+)[\'"]\s*\)', s)
            if m:
                lhs, t = m.group(1), js_tech(m.group(2))
                names = [x.strip().split(':')[-1].strip() for x in lhs.strip('{}').split(',')] if lhs.startswith('{') else [lhs]
                out[i] = [(x, t) for x in names if x]
                continue
            m = re.match(r'require\(\s*[\'"]([^\'"]+)[\'"]\s*\)', s)
            if m: out[i] = [(None, js_tech(m.group(1)))]
    return out


def aliases(ext, lines, sym):
    """names bound to imported tech names in this file: fields/params (Java), assignments/annotations (Py, JS)"""
    al = dict(sym)
    for _ in range(2):
        for line in lines:
            if ext == '.java':
                for m in re.finditer(r'\b([A-Z]\w*)\s*(?:<[^;=(){}]*>)?\s+([a-z]\w*)\s*(?=[;=,)])', line):
                    if m.group(1) in al: al.setdefault(m.group(2), al[m.group(1)])
            elif ext == '.py':
                m = re.match(r'\s*(\w+)\s*(?::\s*[\w.\[\]]+)?\s*=\s*(?:await\s+)?(\w+)', line)
                if m and m.group(2) in al: al.setdefault(m.group(1), al[m.group(2)])
                for m in re.finditer(r'\b(\w+)\s*:\s*(\w+)\b', line):
                    if m.group(2) in al: al.setdefault(m.group(1), al[m.group(2)])
            else:
                m = re.match(r'\s*(?:const|let|var)\s+([\w$]+)\s*=\s*(?:await\s+)?(?:new\s+)?([\w$]+)', line)
                if m and m.group(2) in al: al.setdefault(m.group(1), al[m.group(2)])
    return al


IDENT = re.compile(r'[A-Za-z_$][\w$]*')


def used(line, al):
    t = set()
    for tok in set(IDENT.findall(line)) & al.keys(): t.update(al[tok])
    for fq in re.findall(r'\b((?:org|jakarta|javax|lombok)\.[a-z][\w.]*)', line): t.update(java_tech(fq))
    return t


# ---------------------------------------------------------------- git helpers
def commits(repo):
    out = []
    for line in git(repo, 'log', '--reverse', '--format=%H%x09%an', 'HEAD').splitlines():
        sha, an = line.split('\t')
        out.append((sha, an))
    return out


def scaffold_commits(repo, cs):
    out = set()
    for sha, _ in cs:
        added = [l.split('\t', 1)[1] for l in git(repo, 'show', '--name-status', '--format=', '--no-renames', sha).splitlines()
                 if l.startswith('A\t')]
        for rp, rc in SCAFFOLD:
            if any(re.search(rp, p) and (not rc or re.search(rc, git(repo, 'show', f'{sha}:{p}'))) for p in added):
                out.add(sha)
    return out


def blame(repo, path):
    out, sha, who = [], None, {}
    for line in git(repo, 'blame', '-w', '-M', '-C', '--line-porcelain', 'HEAD', '--', path).splitlines():
        if line.startswith('\t'): out.append((sha, who[sha], line[1:]))
        elif re.match(r'[0-9a-f]{40} ', line): sha = line.split()[0]
        elif line.startswith('author '): who[sha] = line[7:]
    return out


def head_files(repo):
    return git(repo, 'ls-tree', '-r', '--name-only', 'HEAD').splitlines()


# ---------------------------------------------------------------- rules
def old_rule(repo):
    ev = collections.defaultdict(list)
    for p in head_files(repo):
        k, _ = kind(p)
        if k != 'code': continue
        bl = blame(repo, p)
        for i, lst in parse_imports(os.path.splitext(p)[1], [x[2] for x in bl]).items():
            for _, tt in lst:
                for tech in tt: ev[(bl[i][1], tech)].append(f'import {p}:{i + 1}')
    for sha, dev in commits(repo):
        cur = None
        for line in git(repo, 'show', '--format=', '--unified=0', '--no-renames', sha).splitlines():
            if line.startswith('+++ '):
                cur = line[6:] if line.startswith('+++ b/') else None
                continue
            if not cur or not line.startswith('+'): continue
            k, t = kind(cur)
            if k == 'manifest':
                for name in dep_names_line(cur, line[1:]):
                    for tech in dep_tech(cur, name): ev[(dev, tech)].append(f'의존성 줄 {cur}@{sha[:7]}')
            elif k in ('infra', 'infra_ref') and line[1:].strip():
                for tech in t: ev[(dev, tech)].append(f'설정 {cur}@{sha[:7]}')
    return dict(ev)


def new_rule(repo):
    cs = commits(repo)
    scaf = scaffold_commits(repo, cs)
    author = dict(cs)
    skip = lambda sha: sha in scaf or author.get(sha, '').endswith('[bot]')
    sat, weak = collections.defaultdict(list), collections.defaultdict(list)
    files = head_files(repo)
    infra_text = {p: git(repo, 'show', f'HEAD:{p}') for p in files if kind(p)[0] in ('infra', 'infra_ref')}
    used_in_code, lang_n, pending = set(), collections.Counter(), []
    for p in files:
        k, t = kind(p)
        if k not in ('code', 'appcfg', 'infra', 'infra_ref'): continue
        bl, ext = blame(repo, p), os.path.splitext(p)[1]
        if k == 'code':
            lines = [x[2] for x in bl]
            imps = parse_imports(ext, lines)
            al = aliases(ext, lines, {n: tt for lst in imps.values() for n, tt in lst if n and tt})
            for i, (sha, dev, txt) in enumerate(bl):
                if skip(sha) or not txt.strip() or is_comment(ext, txt): continue
                lang_n[(dev, t[0])] += 1
                if i in imps:
                    for _, tt in imps[i]:
                        for tech in tt: weak[(dev, tech)].append(f'import 줄만 {p}:{i + 1}')
                    continue
                for tech in used(txt, al):
                    sat[(dev, tech)].append(f'사용 {p}:{i + 1}')
                    used_in_code.add(tech)
                for rx, db in DBURL:
                    if rx.search(txt): sat[(dev, db)].append(f'DB 주소 {p}:{i + 1}')
                if API.search(txt): sat[(dev, 'API')].append(f'엔드포인트 {p}:{i + 1}')
        elif k == 'appcfg':
            for i, (sha, dev, txt) in enumerate(bl):
                if skip(sha): continue
                for rx, db in DBURL:
                    if rx.search(txt): sat[(dev, db)].append(f'DB 주소 {p}:{i + 1}')
                for key, tech in (('redis', 'Redis'), ('kafka', 'Kafka')):
                    if re.search(rf'^\s*{key}\s*:|\.{key}\.', txt): pending.append((dev, tech, f'앱 설정 {p}:{i + 1}'))
        else:
            n = collections.Counter(dev for sha, dev, txt in bl if not skip(sha) and txt.strip() and not txt.strip().startswith('#'))
            for dev, c in n.items():
                ok = c >= 3
                if k == 'infra_ref' and ok:
                    ok = any(os.path.basename(p) in s or (os.path.dirname(p) and os.path.dirname(p) + '/' in s)
                             for q, s in infra_text.items() if q != p)
                for tech in t: (sat if ok else weak)[(dev, tech)].append(f'설정 {p} {c}줄' + ('' if ok else ' (연결 안 됨)'))
    for dev, tech, e in pending:
        (sat if tech in used_in_code else weak)[(dev, tech)].append(e)
    for (dev, lang), c in lang_n.items():
        if c >= 5: sat[(dev, lang)].append(f'{lang} 내 줄 {c}줄')
    first = {}
    for sha, dev in cs:
        for p in git(repo, 'show', '--name-only', '--format=', '--no-renames', sha).splitlines():
            if kind(p)[0] != 'manifest': continue
            try:
                names = dep_names(p, git(repo, 'show', f'{sha}:{p}'))
            except subprocess.CalledProcessError:
                continue
            for name in names:
                if (p, name) in first: continue
                first[(p, name)] = sha
                if skip(sha): continue
                for tech in dep_tech(p, name): weak[(dev, tech)].append(f'의존성 처음 추가 {p}@{sha[:7]}')
    return dict(sat), {k: v for k, v in weak.items() if k not in sat}


if __name__ == '__main__':
    s, w = new_rule(sys.argv[1])
    for (dev, tech), e in sorted(s.items()): print('충족', dev, tech, e[0])
    for (dev, tech), e in sorted(w.items()): print('정황', dev, tech, e[0])
