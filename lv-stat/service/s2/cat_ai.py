#!/usr/bin/env python3
"""lv-stat 2단계 · AI 기술(ai) 변수 추출기. 버림용 스파이크(2026-11-26, 제품 코드 아님).

usage: python3 -I cat_ai.py P01 [P02 ...]   → out/<pid>/vars-ai.json

- 「문서」 lv-calc AI 기술 줄: LV = (AI 연동 수 단계 + AI 기법 수 단계 + AI 기능 수 단계) ÷ 3. 가점 재료 = 검증된 AI PR 수, AI 도구 흔적 T.
  단계·임계치는 여기서 정하지 않는다(원값만). 문서 시작값(연동 1/2/4/8/15 · 기법 1/2/3/5/7(ML 1/2/3/4/6) · 기능 1/2/3/5/8 · PR 1/2/5/12/30)은 S6이 쓴다.
- 다섯 변수 모두 문서에 정의가 없다(B-37~B-41). 사용자가 2026-11-26 'Claude가 정해서 결과와 이유를 알려 달라'고 해서 후보를 같이 재고
  하나를 골라 definition_choices에 남긴다(「Claude 정의」).
- 받은 레포는 읽기만 한다(git cat-file·blame·rev-list). 실행·빌드·설치·시험하지 않는다. extract는 LLM·네트워크를 쓰지 않는다.
- 근거는 위치(레포 키·경로·줄·커밋·PR 번호)만 남긴다. 코드 내용·이메일·사람 이름은 남기지 않는다.
- 파서: Python(.py·노트북 코드 칸)은 표준 ast. JS/TS·Java/Kotlin·Dart는 주석을 가린 줄 규칙(line-rule) — 이 스파이크에는 tree-sitter가 없다.
  그 밖 언어(Go·Swift·Rust·C#·PHP·Ruby 등)는 규칙 없음 → 흔적이 있으면 S5.
"""
import ast
import collections
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2lib as L  # noqa: E402
import cat_ai_rules as R  # noqa: E402

CAT, KEY = 'ai', 'ai'
MAX_INST = 300
NB_MAX = 512_000
READ_MAX = 1_500_000
CAP_INT, CAP_TECH_PER, CAP_FEAT, CAP_PR, CAP_TOOL = 15, 6, 12, 10, 3      # 사람·변수마다 has_trace 대상 상한(설정값, 본문 12.3)
DEPTH = 4
GENERIC = {'get', 'post', 'put', 'run', 'main', 'call', 'invoke', 'predict', 'generate', 'create', 'update', 'process', 'handle', 'execute', 'chat',
           'send', 'ask', 'query', 'search', 'load', 'save', 'init', 'setup', 'start', 'render', 'build', '__init__', '__call__', 'forward', 'fit',
           'transform', 'complete', 'answer', 'request', 'fetch', 'parse', 'apply', 'step', 'train', 'test', 'evaluate', 'delete', 'list', 'show'}
PY_EXT = ('.py',)
JS_EXT = ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.vue', '.svelte')
JVM_EXT = ('.java', '.kt', '.kts')
DART_EXT = ('.dart',)
NORULE_EXT = ('.go', '.swift', '.rs', '.cs', '.php', '.rb', '.scala', '.cpp', '.cc', '.c', '.m', '.r', '.jl', '.lua', '.ex', '.exs')
GEN_NO_OUT = re.compile(L.GENERATED.pattern.replace('|out|', '|'), re.I)
EXAMPLE = re.compile(r'(^|/)(examples?|samples?|tutorials?)/|\.(example|sample)(\.[^/]*)?$', re.I)
PROMPT_FILE = re.compile(r'(?i)(^|/)prompts?/[^/]+\.(txt|md|j2|jinja2?|ya?ml|json|prompt|tmpl)$|\.prompt(\.md)?$|(^|/)[^/]*prompt[^/]*\.(txt|j2|jinja2?|tmpl)$')


def h8(s):
    return hashlib.sha1(s.encode('utf-8', 'replace')).hexdigest()[:8]


def ext_of(p):
    b = p.rsplit('/', 1)[-1]
    return ('.' + b.rsplit('.', 1)[-1].lower()) if '.' in b else ''


def is_example(p):
    for m in re.finditer(r'(^|/)(examples?|samples?)/', p, re.I):
        before = p[:m.start()].rsplit('/', 1)[-1].lower() if m.start() > 0 else ''
        if before in ('com', 'org', 'net', 'io', 'kr', 'co', 'me', 'dev', 'app'):
            continue
        return True
    return bool(re.search(r'\.(example|sample)(\.[^/]*)?$', p, re.I))


def real_kind(f):
    """s2lib GENERATED의 'out/' 조각이 헥사고날 adapter/out/ 같은 소스 경로를 생성 파일로 잡는다(P01 등). 'out/'만 걸린 파일은 다시 나눈다."""
    k = f['kind']
    if k != 'generated' or GEN_NO_OUT.search(f['path']):
        return k, False
    p = f['path']
    if L.TEST.search(p):
        return 'test', True
    if ext_of(p) == '.ipynb':
        return 'notebook', True
    if f.get('ltype') == 'programming' or f.get('lang') in ('Vue', 'Svelte'):
        return 'code', True
    if L.CONFIG_NAME.search(p):
        return 'config', True
    return 'other', True


# ---------------------------------------------------------------- git 읽기
def read_blobs(repo, files):
    want = [f for f in files if f.get('sha')]
    res = {}
    if not want:
        return res
    by_sha = collections.defaultdict(list)
    for f in want:
        by_sha[f['sha']].append(f['path'])
    rc, out = L.git(repo.dir, 'cat-file', '--batch', inp=('\n'.join(by_sha) + '\n').encode(), timeout=900)
    pos, n = 0, len(out)
    while pos < n:
        nl = out.find(b'\n', pos)
        if nl < 0:
            break
        head = out[pos:nl].decode('utf-8', 'replace').split()
        if len(head) >= 2 and head[-1] == 'missing':
            pos = nl + 1
            continue
        if len(head) != 3:
            break
        sha, size = head[0], int(head[2])
        data = out[nl + 1: nl + 1 + size]
        pos = nl + 1 + size + 1
        txt = data.decode('utf-8', 'replace')
        for p in by_sha.get(sha, []):
            res[p] = txt
    return res


def root_key(repo):
    refs = [x['ref'] for x in repo.refs] or ['HEAD']
    rc, out = L.git(repo.dir, 'rev-list', '--max-parents=0', *refs, timeout=120)
    roots = sorted(set(out.decode().split())) if rc == 0 else []
    return h8(','.join(roots)) if roots else h8(repo.key)


def reachable(repo):
    refs = [x['ref'] for x in repo.refs]
    if not refs:
        return set()
    rc, out = L.git(repo.dir, 'rev-list', *refs, timeout=300)
    return set(out.decode().split()) if rc == 0 else set()


class Own:
    """내 줄. blame(S3)이 있으면 그것. 'out/' 오분류 파일은 여기서 blame을 다시 돈다(읽기만).
    blame이 없는 파일(노트북 등)은 그 경로를 바꾼 커밋이 모두 내 것이면 전부 내 줄, 내 커밋이 없으면 없음, 섞이면 모름(None)."""

    def __init__(self, repo):
        self.repo = repo
        self.own_shas = {c['sha'] for c in repo.commits if c['own']}
        self.touch = collections.defaultdict(lambda: [0, 0])
        for c in repo.commits:
            for f in c['files']:
                self.touch[f['path']][0 if c['own'] else 1] += 1
        self.cache = {}
        self.extra_blame = 0

    def lines(self, path, reblame=False):
        """-> (방식, 집합 또는 None)"""
        ck = (path, bool(reblame))
        if ck in self.cache:
            return self.cache[ck]
        s = self.repo.own_line_set(path)
        if s is not None:
            res = ('blame', s)
        elif reblame and self.touch.get(path, (0, 0))[0]:
            res = self._blame(path)
        else:
            o, t = self.touch.get(path, (0, 0))
            res = ('commits_all_mine', None) if (o and not t) else (('commits_none_mine', set()) if not o else ('mixed_unknown', None))
        self.cache[ck] = res
        return res

    def _blame(self, path):
        f = self.repo.file(path)
        if not f:
            return ('mixed_unknown', None)
        rc, out = L.git(self.repo.dir, 'blame', '--porcelain', f['ref'], '--', path, timeout=300)
        if rc != 0:
            return ('mixed_unknown', None)
        self.extra_blame += 1
        mine, cur, n = set(), None, 0
        for line in out.decode('utf-8', 'replace').splitlines():
            m = re.match(r'^([0-9a-f]{40}) \d+ (\d+)', line)
            if m:
                cur = (m.group(1), int(m.group(2)))
                continue
            if line.startswith('\t') and cur:
                if cur[0] in self.own_shas:
                    mine.add(cur[1])
                cur = None
        return ('blame(re)', mine)

    def is_mine(self, path, line, reblame=False):
        m, s = self.lines(path, reblame)
        if s is not None:
            return line in s
        if m == 'commits_all_mine':
            return True
        return None

    def has_mine(self, path, reblame=False):
        m, s = self.lines(path, reblame)
        if s is not None:
            return bool(s)
        return m == 'commits_all_mine'


# ---------------------------------------------------------------- 노트북
def strip_magics(src):
    return '\n'.join('' if l.lstrip().startswith(('%', '!', '?')) else l for l in src.split('\n'))


def nb_cells(raw):
    try:
        nb = json.loads(raw)
    except Exception:
        return None
    cells = nb.get('cells') if isinstance(nb, dict) else None
    if cells is None and isinstance(nb, dict) and nb.get('worksheets'):
        cells = [c for w in nb['worksheets'] for c in w.get('cells', [])]
    res = []
    for i, c in enumerate(cells or []):
        if not isinstance(c, dict) or c.get('cell_type') != 'code':
            continue
        src = c.get('source', c.get('input', ''))
        if isinstance(src, list):
            src = ''.join(src)
        res.append((i, strip_magics(src or '')))
    return res


def nb_raw_ranges(raw):
    lines = raw.split('\n')
    res, cell, start = {}, -1, None
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith('"cell_type"'):
            cell += 1
        elif s.startswith('"source"'):
            if s.endswith('['):
                start = i + 1
            else:
                res[cell] = (i, i)
        elif start is not None and (s == ']' or s == '],'):
            res[cell] = (start, max(start, i - 1))
            start = None
    return res


# ---------------------------------------------------------------- Python(ast)
HTTP_DECO = re.compile(r'\.(get|post|put|delete|patch|route|websocket|api_route|head|options|api_view)$')
HTTP_RECV = re.compile(r'^(fastapi\.(FastAPI|APIRouter)\(\)|flask\.(Flask|Blueprint)\(\)|starlette\.|sanic\.|quart\.|ninja\.(NinjaAPI|Router)\(\)|aiohttp\.web\.RouteTableDef\(\)|rest_framework\.decorators)')
BOT_ATTR = {'command', 'event', 'hybrid_command', 'slash_command', 'message', 'message_handler', 'callback_query_handler', 'listen', 'action',
            'shortcut', 'callback_query', 'on_message'}
CLI_DECO = re.compile(r'^(typer\.Typer\(\)\.command|click\.(command|group)|click\.group\(\)\.command|fire\.Fire)')


class PyScan:
    def __init__(self, path, units):
        self.path = path
        self.alias, self.env = {}, {}
        self.sites, self.tech, self.funcs, self.calls, self.entries, self.entry_for = [], [], [], [], [], {}
        self.hosts, self.imports, self.err = [], set(), None
        self.module_main, self.streamlit, self.gradio = False, False, False
        self.has_defs = False
        self.http_lib = False
        trees = []
        for cell, code in units:
            try:
                trees.append((cell, ast.parse(code)))
            except (SyntaxError, ValueError) as e:
                self.err = (cell, getattr(e, 'lineno', None))
        for cell, tree in trees:
            for node in ast.walk(tree):
                for ch in ast.iter_child_nodes(node):
                    ch._p = node
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.alias[(a.asname or a.name.split('.')[0])] = a.name if a.asname else a.name.split('.')[0]
                        self.imports.add(a.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    for a in node.names:
                        self.alias[a.asname or a.name] = node.module + '.' + a.name
                    self.imports.add(node.module.split('.')[0])
        self.cli_iface = bool(self.imports & {'argparse', 'click', 'typer', 'fire', 'docopt'}) or any('sys.argv' in c for _, c in units)
        self.streamlit = 'streamlit' in self.imports
        self.gradio = 'gradio' in self.imports
        self.http_lib = bool(self.imports & {'requests', 'httpx', 'aiohttp', 'urllib', 'urllib3', 'http'})
        self.ret = {}
        for _ in range(2):
            for cell, tree in trees:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for rn in ast.walk(node):
                            if isinstance(rn, ast.Return) and rn.value is not None:
                                rr = self.res(rn.value)
                                if rr and '.' in rr:
                                    self.ret[node.name] = rr
                                    break
                    if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                        r = self.res(node.value)
                        if r:
                            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                                k = self.tname(t)
                                if k:
                                    self.env[k] = r
                    elif isinstance(node, (ast.With, ast.AsyncWith)):
                        for it in node.items:
                            if it.optional_vars is not None:
                                r = self.res(it.context_expr)
                                k = self.tname(it.optional_vars)
                                if r and k:
                                    self.env[k] = r
        for cell, tree in trees:
            self.cell = cell
            self._walk(tree, None, False)

    # -- 풀이
    def tname(self, t):
        if isinstance(t, ast.Name):
            return t.id
        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in ('self', 'cls'):
            return t.value.id + '.' + t.attr
        return None

    def res(self, node):
        if isinstance(node, ast.Await):
            return self.res(node.value)
        if isinstance(node, ast.Name):
            return self.env.get(node.id) or self.alias.get(node.id)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in ('self', 'cls'):
                return self.env.get(node.value.id + '.' + node.attr)
            b = self.res(node.value)
            return (b + '.' + node.attr) if b else None
        if isinstance(node, ast.Call):
            n = self.simple(node.func)
            if n and n in getattr(self, 'ret', {}) and not (isinstance(node.func, ast.Name) and (n in self.alias or n in self.env)):
                return self.ret[n]
            b = self.res(node.func)
            return (b + '()') if b else None
        return None

    def chain(self, func):
        parts = []
        while isinstance(func, ast.Attribute):
            parts.append(func.attr)
            func = func.value
        return '.'.join(reversed(parts))

    def has_mod(self, mod):
        return mod in self.imports or any(v == mod or v.startswith(mod + '.') for v in self.alias.values())

    @staticmethod
    def simple(func):
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    def kwnames(self, call):
        return {k.arg for k in call.keywords if k.arg}

    def first_str(self, call, kw=None):
        if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
            return call.args[0].value
        for k in call.keywords:
            if kw and k.arg == kw and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str):
                return k.value.value
        return None

    # -- 걷기(함수 맥락 유지)
    def _walk(self, node, fidx, in_main):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.has_defs = True
                cls = node.name if isinstance(node, ast.ClassDef) else None
                bases = [self.simple(b) or '' for b in node.bases] if isinstance(node, ast.ClassDef) else []
                decos = []
                for d in ch.decorator_list:
                    dn = d.func if isinstance(d, ast.Call) else d
                    decos.append((self.res(dn) or '', self.simple(dn) or '', (self.first_str(d) if isinstance(d, ast.Call) else None),
                                  (self.simple(dn.value) if isinstance(dn, ast.Attribute) and isinstance(dn.value, (ast.Name, ast.Attribute)) else None)))
                params = [a.arg for a in ch.args.args]
                f = dict(name=ch.name, cell=self.cell, start=ch.lineno, end=getattr(ch, 'end_lineno', ch.lineno), cls=cls, bases=bases,
                         decos=decos, params=params, parent=fidx)
                self.funcs.append(f)
                idx = len(self.funcs) - 1
                self._entry_of_func(f, idx)
                self._walk(ch, idx, in_main)
                continue
            if isinstance(ch, ast.If) and fidx is None and self._is_main_guard(ch.test):
                self.module_main = True
                self._walk(ch, fidx, True)
                continue
            if isinstance(ch, ast.Call):
                self._call(ch, fidx, in_main)
            elif isinstance(ch, ast.Constant) and isinstance(ch.value, str) and len(ch.value) < 4000:
                hh = R.host_hit(ch.value)
                if hh:
                    self.hosts.append(dict(cell=self.cell, line=ch.lineno, prov=hh[0], kind=hh[1], func=fidx))
                if R.VEC_SQL.search(ch.value) and re.search(r'(?i)\b(select|order by)\b', ch.value):
                    self.tech.append(dict(tech='embedding_search', cell=self.cell, line=ch.lineno, strong=True, rule='pgvector-sql', func=fidx))
            elif isinstance(ch, ast.BinOp) and isinstance(ch.op, ast.BitOr):
                self._pipe(ch, fidx)
            self._walk(ch, fidx, in_main)

    @staticmethod
    def _is_main_guard(t):
        return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == '__name__'
                and any(isinstance(c, ast.Constant) and c.value == '__main__' for c in t.comparators))

    def _entry_of_func(self, f, idx):
        base = os.path.basename(self.path).lower()
        for full, simple, arg, recv in f['decos']:
            if HTTP_DECO.search('.' + simple) and (HTTP_RECV.search(full) or (recv or '').lower() in ('app', 'router', 'bp', 'api', 'blueprint', 'routes', 'api_router', 'route', 'v1')):
                self.entries.append(dict(kind='http', key=f"{simple.upper()} {arg or f['name']}", func=idx, line=f['start'], cell=f['cell']))
                return
            if simple == 'api_view':
                self.entries.append(dict(kind='http', key=f"DRF {f['name']}", func=idx, line=f['start'], cell=f['cell']))
                return
            if simple in BOT_ATTR and ((recv or '').lower() in ('bot', 'client', 'tree', 'dp', 'app', 'slack_app', 'router', 'commands', 'app_commands')
                                       or re.match(r'^(discord|slack_bolt|aiogram|telegram|nextcord|disnake)', full)):
                if not (simple == 'message' and (recv or '').lower() == 'router' and 'aiogram' not in full):
                    self.entries.append(dict(kind='bot', key=f"bot {simple} {arg or f['name']}", func=idx, line=f['start'], cell=f['cell']))
                    return
            if CLI_DECO.search(full) or (simple == 'command' and (recv or '').lower() in ('cli', 'typer_app', 'group')):
                self.entries.append(dict(kind='cli', key=f"cli {f['name']}", func=idx, line=f['start'], cell=f['cell']))
                return
        if base in ('views.py', 'viewsets.py', 'api.py') or base.endswith('_views.py'):
            if (f['params'][:1] == ['request']) or (f['cls'] and f['name'] in ('get', 'post', 'put', 'patch', 'delete', 'list', 'create', 'retrieve',
                                                                                   'update', 'partial_update', 'destroy', 'perform_create')):
                self.entries.append(dict(kind='http', key=f"django {f['cls'] + '.' if f['cls'] else ''}{f['name']}", func=idx, line=f['start'], cell=f['cell']))

    def _pipe(self, node, fidx):
        names = []
        for side in (node.left, node.right):
            r = self.res(side) or ''
            names.append(r)
        joined = ' '.join(names)
        if re.search(r'(PromptTemplate|ChatPromptTemplate)', joined) and (R.LC_MOD.search(names[0] or '') or R.LC_MOD.search(names[1] or '') or
                                                                           any(re.search(r'\.(' + '|'.join(R.LC_CTOR) + r')\(\)$', n or '') for n in names)):
            self.tech.append(dict(tech='prompt_chain', cell=self.cell, line=node.lineno, strong=True, rule='lcel-pipe', func=fidx))

    def _site(self, call, fidx, prov, kind, local, rule):
        self.sites.append(dict(cell=self.cell, line=call.lineno, prov=prov, kind=kind, local=local, rule=rule, func=fidx,
                               kw=sorted(self.kwnames(call))))

    def _used(self, call):
        p = getattr(call, '_p', None)
        if isinstance(p, (ast.Assign, ast.AnnAssign)):
            tg = p.targets if isinstance(p, ast.Assign) else [p.target]
            names = {self.tname(t) for t in tg} - {None}
            return bool(names) and any(n in self._loads() for n in names)
        return True

    def _loads(self):
        if not hasattr(self, '_ld'):
            self._ld = collections.Counter()
        return self._ld

    def _call(self, call, fidx, in_main):
        r = self.res(call.func) or ''
        simple = self.simple(call.func) or ''
        kws = self.kwnames(call)
        self.calls.append(dict(name=simple, cell=self.cell, line=call.lineno, func=fidx, main=in_main))
        hit = False
        if r:
            for rx, prov, kind, local in R.PY_API:
                if rx.search(r):
                    self._site(call, fidx, prov, kind, local, 'py-sdk')
                    hit = True
                    break
            if not hit and r in ('transformers.pipeline', 'transformers.pipelines.pipeline'):
                task = self.first_str(call, 'task') or 'model'
                self._site(call, fidx, 'Hugging Face(로컬)', R.HF_TASK.get(task, 'model-inference'), True, 'hf-pipeline')
                hit = True
            if not hit and re.search(r'^transformers\.(Auto\w+|\w+For\w+|\w+Model|\w+LMHeadModel)\.from_pretrained$', r):
                self._site(call, fidx, 'Hugging Face(로컬)', 'model-inference', True, 'hf-from-pretrained')
                self.tech.append(dict(tech='_pretrained', cell=self.cell, line=call.lineno, strong=True, rule='hf-pretrained', func=fidx,
                                      causal='CausalLM' in r))
                hit = True
            m = R.LC_MOD.search(r + '()')
            if not hit and m and m.group(2) in R.LC_CTOR:
                prov, kind, local = R.LC_CTOR[m.group(2)]
                self._site(call, fidx, prov, kind, local, 'langchain-ctor')
                self.sites[-1]['ctor'] = True
                hit = True
            if not hit and re.search(r'^boto3\.(client|Session\(\)\.client)$', r):
                svc = self.first_str(call, 'service_name') or ''
                amap = {'bedrock-runtime': ('AWS Bedrock', 'chat'), 'rekognition': ('AWS Rekognition', 'vision'), 'transcribe': ('AWS Transcribe', 'speech-to-text'),
                        'polly': ('AWS Polly', 'text-to-speech'), 'comprehend': ('AWS Comprehend', 'nlp'), 'textract': ('AWS Textract', 'vision'),
                        'sagemaker-runtime': ('AWS SageMaker', 'model-inference')}
                if svc in amap:
                    self._site(call, fidx, amap[svc][0], amap[svc][1], False, 'boto3-ai')
                    hit = True
            self._tech_call(call, r, simple, kws, fidx)
        else:
            self._tech_unresolved(call, simple, kws, fidx)
        if not hit and isinstance(call.func, ast.Attribute) and not (r and re.match(r'^(openai|anthropic|google|ollama|groq|sentence_transformers|whisper|faster_whisper)\b', r)):
            suf = self.chain(call.func)
            recv = suf.rsplit('.', 1)[0] if '.' in suf else ''
            base = call.func.value
            while isinstance(base, ast.Attribute):
                base = base.value
            btxt = (base.id if isinstance(base, ast.Name) else '') + '.' + recv
            for rx, mod, prov, kind in R.PY_SUFFIX:
                if suf.rsplit('.', 1)[-1] in ('transcribe', 'encode', 'chat', 'generate', 'send_message', 'generate_content', 'generate_content_async') and \
                        '.' not in suf.rsplit('.', 1)[0] and not re.search(r'(?i)model|whisper|client|llm|genai|gemini|chat|encoder|embed|sbert|^st\b|ollama', btxt):
                    continue
                if rx.search(suf) and self.has_mod(mod):
                    self._site(call, fidx, prov, kind, bool(R.LOCAL_PROV.search(prov)), 'py-sdk-suffix')
                    break
        # 엔트리: 함수를 넘기는 등록(Gradio·텔레그램·Streamlit on_click·__main__)
        if r.startswith('gradio.') or (self.gradio and simple in ('click', 'submit', 'change', 'then', 'select', 'upload', 'Interface', 'ChatInterface')):
            for a in list(call.args[:1]) + [k.value for k in call.keywords if k.arg in ('fn', 'callback')]:
                n = self.simple(a) if isinstance(a, (ast.Name, ast.Attribute)) else None
                if n:
                    self.entry_for.setdefault(n, ('screen', f'gradio {n}'))
        if re.search(r'(CommandHandler|MessageHandler|CallbackQueryHandler|add_handler|register_message_handler)$', r or simple):
            for a in call.args[:3]:
                n = self.simple(a) if isinstance(a, (ast.Name, ast.Attribute)) else None
                if n and n not in ('filters',):
                    self.entry_for.setdefault(n, ('bot', f'bot {n}'))
        if self.streamlit:
            for k in call.keywords:
                if k.arg in ('on_click', 'on_change', 'on_submit'):
                    n = self.simple(k.value) if isinstance(k.value, (ast.Name, ast.Attribute)) else None
                    if n:
                        self.entry_for.setdefault(n, ('screen', f'streamlit {os.path.basename(self.path)}'))

    def _tech(self, tech, call, strong, rule, fidx, **kw):
        self.tech.append(dict(tech=tech, cell=self.cell, line=call.lineno, strong=strong, rule=rule, func=fidx, **kw))

    def _tech_call(self, call, r, simple, kws, fidx):
        last = r.rsplit('.', 1)[-1].replace('()', '')
        mod = r.split('.', 1)[0]
        if mod == 'sklearn' or r.startswith('sklearn'):
            if last == 'train_test_split':
                self._tech('data_split', call, True, 'sklearn-split', fidx)
            elif last in R.SK_CV:
                self._tech('cross_validation', call, True, 'sklearn-cv', fidx)
            elif last in R.SK_SEARCH:
                self._tech('hyperparam_search', call, True, 'sklearn-search', fidx)
            elif last in R.SK_PIPE:
                self._tech('preprocess_pipeline', call, True, 'sklearn-pipeline', fidx)
            elif last in R.SK_PREP:
                self._tech('preprocess_pipeline', call, False, 'sklearn-prep-only', fidx)
            elif last in R.SK_METRICS:
                self._tech('eval_metrics', call, True, 'sklearn-metrics', fidx)
        if r.startswith('skopt.') and last == 'BayesSearchCV':
            self._tech('hyperparam_search', call, True, 'skopt', fidx)
        if re.search(r'^(optuna\.create_study|keras_tuner\.|kerastuner\.|ray\.tune\.|hyperopt\.fmin)', r):
            self._tech('hyperparam_search', call, True, 'tuner', fidx)
        if r.startswith('torchmetrics.') or re.search(r'^(evaluate\.load|torcheval\.)', r):
            self._tech('eval_metrics', call, True, 'metrics-lib', fidx)
        if r in ('torch.utils.data.random_split', 'torch.utils.data.dataset.random_split'):
            self._tech('data_split', call, True, 'torch-random-split', fidx)
        if re.search(r'^(torchvision\.transforms(\.v2)?\.Compose|albumentations\.Compose)$', r):
            self._tech('preprocess_pipeline', call, True, 'transforms-compose', fidx)
        # 학습
        if last in ('fit', 'fit_generator', 'partial_fit') and R.ML_EST_MOD.search(r) and \
                not re.search(r'^sklearn\.(preprocessing|impute|feature_extraction|feature_selection|decomposition|compose|pipeline)\b', r) and \
                not re.search(r'\.(' + '|'.join(R.SK_PREP) + r')\(\)', r):
            self._tech('model_training', call, True, 'estimator-fit', fidx)
            if 'validation_split' in kws:
                self._tech('data_split', call, True, 'keras-validation-split', fidx)
        if re.search(r'^(xgboost|lightgbm|catboost)\.(train|cv)$', r):
            self._tech('model_training', call, True, 'boost-train', fidx)
            if r.endswith('.cv'):
                self._tech('cross_validation', call, True, 'boost-cv', fidx)
        if re.search(r'^(transformers\.(Trainer|Seq2SeqTrainer)|trl\.(SFTTrainer|DPOTrainer|RewardTrainer|PPOTrainer|GRPOTrainer))\(\)\.train$', r):
            self._tech('model_training', call, True, 'hf-trainer', fidx)
            self._tech('_trainer', call, True, 'hf-trainer', fidx, trl=r.startswith('trl'))
        if re.search(r'^ultralytics\.(YOLO|RTDETR)\(\)\.train$', r):
            self._tech('model_training', call, True, 'yolo-train', fidx)
            self._tech('_pretrained_train', call, True, 'yolo-pretrained-train', fidx)
        if re.search(r'^(peft\.(get_peft_model|LoraConfig|prepare_model_for_kbit_training)|trl\.(SFTTrainer|DPOTrainer))$', r) or \
                re.search(r'^openai\.(?:Async)?OpenAI\(\)\.fine_tuning\.jobs\.create$|^openai\.FineTuningJob\.create$', r):
            self._tech('fine_tuning', call, True, 'ft-lib', fidx)
        if re.search(r'^(keras|tensorflow\.keras|tf\.keras)\.applications\.\w+$|^torchvision\.models\.\w+$|^timm\.create_model$', r) and (kws & R.PRETRAIN_KW):
            self._tech('_pretrained', call, True, 'vision-pretrained', fidx, causal=False)
        # 저장
        if r in ('joblib.dump', 'pickle.dump', 'torch.save', 'tensorflow.saved_model.save', 'dill.dump', 'cloudpickle.dump', 'skops.io.dump'):
            arg = self.simple(call.args[0]) if call.args and isinstance(call.args[0], (ast.Name, ast.Attribute)) else ''
            strong = r in ('torch.save', 'tensorflow.saved_model.save') or bool(re.search(r'(?i)model|clf|classifier|regressor|estimator|pipe|xgb|lgb|rf|svm|knn', arg or ''))
            self._tech('model_save', call, strong, 'model-dump', fidx)
        if last in ('save', 'save_model', 'save_pretrained', 'save_weights') and (R.ML_EST_MOD.search(r) or r.startswith(('transformers.', 'ultralytics.'))):
            self._tech('model_save', call, True, 'model-save', fidx)
        if r in ('joblib.load', 'pickle.load', 'torch.load', 'tensorflow.keras.models.load_model', 'keras.models.load_model', 'tensorflow.saved_model.load',
                 'tf.keras.models.load_model', 'onnxruntime.InferenceSession', 'xgboost.Booster', 'lightgbm.Booster', 'keras.saving.load_model'):
            self._tech('_model_load', call, True, 'model-load', fidx)
        # LLM 기법
        if mod in ('langchain', 'langchain_core', 'langchain_community', 'langchain_openai', 'langchain_classic', 'langgraph', 'llama_index', 'crewai', 'agents',
                   'autogen', 'langchain_text_splitters', 'langchain_chroma', 'langchain_pinecone', 'langchain_huggingface', 'langchain_google_genai',
                   'langchain_ollama', 'langchain_anthropic', 'langchain_postgres', 'langchain_qdrant'):
            if last in R.LC_RAG or (last == 'from_chain_type' and 'RetrievalQA' in r):
                self._tech('rag', call, True, 'lc-retrieval-chain', fidx)
            if last in R.LC_AGENT and (mod != 'agents' or last == 'Runner') or (mod == 'crewai' and last in ('Agent', 'Crew')) or \
                    re.search(r'^langgraph\.prebuilt\.create_react_agent$|^agents\.Runner\.run', r):
                self._tech('agent', call, True, 'agent-lib', fidx)
            if last in R.LC_STRUCT:
                self._tech('structured_output', call, True, 'lc-parser', fidx)
            if last in R.LC_PROMPT:
                self._tech('prompt_template', call, True, 'lc-prompt', fidx)
            if last in R.LC_CHAIN:
                self._tech('prompt_chain', call, True, 'lc-chain', fidx)
            if last in ('bind_tools', 'StructuredTool', 'Tool', 'from_function', 'create_retriever_tool'):
                self._tech('tool_calling', call, True, 'lc-tools', fidx)
            if r.startswith('llama_index') and re.search(r'VectorStoreIndex', r):
                self._tech('embedding_search', call, True, 'llamaindex-index', fidx)
                if re.search(r'as_query_engine|as_chat_engine', r):
                    self._tech('rag', call, True, 'llamaindex-query-engine', fidx)
        if r.startswith('instructor.') and re.search(r'\.(create|create_with_completion)$', r):
            self._tech('structured_output', call, True, 'instructor', fidx)
        if last == 'with_structured_output':
            self._tech('structured_output', call, True, 'with-structured-output', fidx)
        if R.VEC_SEARCH.search(r):
            self._tech('embedding_search', call, True, 'vector-search', fidx)
        if re.search(r'^(mcp\.server\.fastmcp\.FastMCP|fastmcp\.FastMCP|mcp\.server\.Server|mcp\.server\.lowlevel\.Server|mcp\.ClientSession|mcp\.client\.\w+\.\w+_client|mcp\.server\.stdio\.stdio_server)$', r):
            self._tech('mcp', call, True, 'mcp-sdk', fidx)
        if re.search(r'^(ragas\.evaluate|deepeval\.|langsmith\.evaluation\.evaluate|trulens|promptfoo)', r):
            self._tech('llm_eval', call, True, 'eval-lib', fidx)
        # AI 호출 인자: 도구·구조화 출력
        if self.sites and self.sites[-1]['line'] == call.lineno and self.sites[-1]['cell'] == self.cell:
            kw = set(self.sites[-1]['kw'])
            if kw & {'tools', 'functions', 'tool_choice', 'function_call'}:
                self._tech('tool_calling', call, True, 'ai-call-tools-arg', fidx)
            if kw & {'response_format', 'text_format', 'response_schema', 'response_mime_type', 'output_type'} or \
                    re.search(r'\.parse$', r):
                self._tech('structured_output', call, True, 'ai-call-format-arg', fidx)
            if 'generation_config' in kw:
                for k in call.keywords:
                    if k.arg == 'generation_config' and isinstance(k.value, ast.Dict):
                        ks = {x.value for x in k.value.keys if isinstance(x, ast.Constant)}
                        if ks & {'response_mime_type', 'response_schema'}:
                            self._tech('structured_output', call, True, 'gemini-json', fidx)

    def _tech_unresolved(self, call, simple, kws, fidx):
        ml = self.imports & {'sklearn', 'xgboost', 'lightgbm', 'catboost', 'keras', 'tensorflow', 'torch', 'statsmodels', 'prophet'}
        if simple in ('fit', 'fit_generator') and ml:
            self._tech('model_training', call, False, 'fit-unresolved', fidx)
            if 'validation_split' in kws:
                self._tech('data_split', call, True, 'keras-validation-split', fidx)
        if simple == 'backward' and 'torch' in self.imports:
            self._tech('_backward', call, True, 'torch-backward', fidx)
        if simple == 'step' and 'torch' in self.imports:
            self._tech('_optstep', call, True, 'torch-step', fidx)
        if simple in ('evaluate',) and ml & {'keras', 'tensorflow'}:
            self._tech('eval_metrics', call, False, 'keras-evaluate', fidx)
        if simple in ('save', 'save_model', 'save_weights') and ml:
            self._tech('model_save', call, False, 'save-unresolved', fidx)
        if simple in ('predict', 'predict_proba') and ml:
            self._tech('_predict', call, True, 'predict', fidx)
        if simple in ('similarity_search', 'similarity_search_with_score', 'as_retriever', 'max_marginal_relevance_search'):
            self._tech('embedding_search', call, False, 'vector-search-unresolved', fidx)


def scan_python(path, text, is_nb):
    units = nb_cells(text) if is_nb else [(None, text)]
    if units is None:
        return None
    s = PyScan(path, units)
    # LangChain 생성자는 그 이름이 다시 쓰였을 때만(「문서」 규칙 8: 실제로 호출한 곳)
    loads = collections.Counter()
    for cell, code in units:
        for m in re.finditer(r'\b(self\.)?([A-Za-z_]\w*)\b', code):
            loads[(m.group(1) or '') + m.group(2)] += 1
    keep = []
    for x in s.sites:
        if x.get('ctor'):
            name = None
            for k, v in s.env.items():
                pass
            # 같은 줄에서 대입된 이름을 찾는다
            line_txt = ''
            for cell, code in units:
                if cell == x['cell']:
                    ls = code.split('\n')
                    line_txt = ls[x['line'] - 1] if 0 < x['line'] <= len(ls) else ''
            m = re.match(r'^\s*((?:self\.)?[A-Za-z_]\w*)\s*(?::[^=]+)?=\s*', line_txt)
            if m and loads[m.group(1)] < 2:
                x['unused'] = True
        keep.append(x)
    s.sites = keep
    return s


# ---------------------------------------------------------------- 줄 규칙(JS/TS·JVM·Dart)
def mask_comments(text, kind):
    if kind in ('js', 'jvm', 'dart'):
        text = re.sub(r'/\*.*?\*/', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text, flags=re.S)
        text = re.sub(r'(^|[^:"\'\\])//[^\n]*', lambda m: m.group(1) + ' ' * (len(m.group(0)) - len(m.group(1))), text)
        if kind == 'js':
            text = re.sub(r'<!--.*?-->', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text, flags=re.S)
    return text


def mask_strings(text):
    def rep(m):
        return m.group(0)[0] + re.sub(r'[^\n]', ' ', m.group(0)[1:-1]) + m.group(0)[-1]
    return re.sub(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`', rep, text)


JS_FUNC = [re.compile(r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\('),
           re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::\s*[^=]+)?=>'),
           re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function\b'),
           re.compile(r'^\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+|override\s+)*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::\s*[^{]+)?\{\s*$')]
JS_NOT = {'if', 'for', 'while', 'switch', 'catch', 'function', 'return', 'else', 'do', 'try', 'constructor'}
JS_ROUTE = re.compile(r'''\b(app|router|server|api|routes?|r|fastify|route)\s*\.\s*(get|post|put|delete|patch|all)\s*\(\s*['"`]([^'"`]+)['"`]''')
NEST_ROUTE = re.compile(r'''@(Get|Post|Put|Delete|Patch|All|Sse|MessagePattern)\s*\(\s*['"`]?([^'"`)]*)''')
JVM_FUNC = [re.compile(r'^\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:public|protected|private|static|final|synchronized|abstract|default|\s)*[\w<>\[\],.? ]+\s+([a-zA-Z_]\w*)\s*\([^;]*$'),
            re.compile(r'^\s*(?:override\s+|suspend\s+|private\s+|public\s+|internal\s+|protected\s+|open\s+|inline\s+)*fun\s+(?:<[^>]+>\s*)?(?:[\w.]+\.)?([a-zA-Z_]\w*)\s*\(')]
JVM_NOT = {'if', 'for', 'while', 'switch', 'catch', 'return', 'new', 'else', 'synchronized', 'super', 'this'}
SPRING_ROUTE = re.compile(r'''@(Get|Post|Put|Delete|Patch|Request|Message)Mapping\s*(?:\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*"([^"]*)")?''')
DART_FUNC = re.compile(r'^\s*(?:static\s+|Future<[^>]*>\s+|Stream<[^>]*>\s+|void\s+|[\w<>?,\s]+\s+)?([a-zA-Z_]\w*)\s*\([^;]*\)\s*(?:async\s*\*?)?\s*\{\s*$')
SCREEN_PATH = re.compile(r'(?i)(^|/)(pages|app|components|views|screens|routes|src|containers|features|widgets|ui)/')
SERVER_PATH = re.compile(r'(?i)(^|/)(api|server|backend|routes?/api|functions|lambda|controllers?|services?)/')


def block_end(masked_lines, start_idx):
    """start_idx(0부터) 줄에서 시작하는 { } 블록의 끝 줄 번호(0부터). 못 찾으면 start_idx + 60."""
    depth, opened = 0, False
    for i in range(start_idx, min(len(masked_lines), start_idx + 3000)):
        for ch in masked_lines[i]:
            if ch == '{':
                depth += 1
                opened = True
            elif ch == '}':
                depth -= 1
                if opened and depth <= 0:
                    return i
        if not opened and i > start_idx + 3:
            return start_idx
    return min(len(masked_lines) - 1, start_idx + 60)


class LineScan:
    """JS/TS·JVM·Dart 줄 규칙. 함수 = 머리 줄 정규식 + 중괄호 블록. 호출 그래프는 이름으로."""

    def __init__(self, path, text, lang):
        self.path, self.lang = path, lang
        self.err = None
        kind = {'js': 'js', 'jvm': 'jvm', 'dart': 'dart'}[lang]
        masked = mask_comments(text, kind)
        lines = masked.split('\n')
        nostr = mask_strings(masked).split('\n')
        self.n = len(lines)
        self.sites, self.tech, self.funcs, self.calls, self.entries, self.entry_for, self.hosts = [], [], [], [], [], {}, []
        self.imports, self.provs = set(), set()
        ext = ext_of(path)
        # import
        for i, l in enumerate(lines, 1):
            if lang == 'js':
                for m in R.JS_IMPORT.finditer(l):
                    pkg = m.group(1)
                    self.imports.add(pkg)
                    prov = R.JS_PKG.get(pkg) or next((v for k, v in R.JS_PKG_PREFIX if pkg.startswith(k)), None)
                    if prov:
                        self.provs.add(prov)
            elif lang == 'jvm':
                m = R.JVM_IMPORT.match(l)
                if m:
                    for k, v in R.JVM_PKG:
                        if m.group(1).startswith(k):
                            self.provs.add(v)
            elif lang == 'dart':
                for k, v in R.DART_PKG:
                    if k in l and re.match(r'^\s*import\b', l):
                        self.provs.add(v)
        if lang == 'jvm' and not self.provs:
            # Kotlin·Java에서 같은 패키지 안이라 import 없이 쓰는 경우는 놓친다(흔적으로 넘김)
            pass
        calls_tbl = {'js': R.JS_CALLS, 'jvm': R.JVM_CALLS, 'dart': R.DART_CALLS}[lang]
        http_rx = R.JS_HTTP if lang == 'js' else R.JVM_HTTP
        self.http_lib = bool(http_rx.search(masked)) or ('http' in self.imports) or bool(re.search(r'package:http/|package:dio/', masked))
        # 함수 머리
        heads = []
        for i, l in enumerate(nostr):
            name = None
            if lang == 'js':
                for rx in JS_FUNC:
                    m = rx.match(l)
                    if m and m.group(1) not in JS_NOT:
                        name = m.group(1)
                        break
                mr = JS_ROUTE.search(l)
                if mr and not name:
                    name = f'route@{i + 1}'
                    self.entries.append(dict(kind='http', key=f'{mr.group(2).upper()} {lines[i][mr.start(3):mr.end(3)] if False else _route_path(lines[i])}', func=None, line=i + 1))
            elif lang == 'jvm':
                for rx in JVM_FUNC:
                    m = rx.match(l)
                    if m and m.group(1) not in JVM_NOT and not re.match(r'^\s*(return|new|else|throw)\b', l):
                        name = m.group(1)
                        break
            else:
                m = DART_FUNC.match(l)
                if m and m.group(1) not in JVM_NOT:
                    name = m.group(1)
            if name:
                end = block_end(nostr, i)
                heads.append((i, end, name))
        for i, end, name in heads:
            self.funcs.append(dict(name=name, cell=None, start=i + 1, end=end + 1, decos=[], params=[]))
        # 엔트리(함수 단위)
        cls_screen = None
        for fi, f in enumerate(self.funcs):
            pre = '\n'.join(lines[max(0, f['start'] - 4):f['start']])
            if lang == 'jvm':
                m = SPRING_ROUTE.search(pre)
                if m:
                    self.entries.append(dict(kind='http', key=f"{m.group(1).upper()} {m.group(2) or f['name']}", func=fi, line=f['start']))
                elif re.search(r'@Composable', pre):
                    self.entries.append(dict(kind='screen', key=f"compose {f['name']}", func=fi, line=f['start']))
            if lang == 'js':
                m = NEST_ROUTE.search(pre)
                if m and path.endswith('.ts'):
                    self.entries.append(dict(kind='http', key=f"{m.group(1).upper()} {m.group(2) or f['name']}", func=fi, line=f['start']))
                if f['name'].startswith('route@'):
                    for e in self.entries:
                        if e['line'] == f['start'] and e['func'] is None:
                            e['func'] = fi
                if re.search(r'(^|/)(app/(.*/)?api/(.+/)?route|pages/api/.+)\.(t|j)sx?$', path) and f['name'] in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'handler', 'default'):
                    self.entries.append(dict(kind='http', key=f"{f['name']} /{_next_api_path(path)}", func=fi, line=f['start']))
        if lang == 'js' and re.search(r'(^|/)(app/(.*/)?api/(.+/)?route|pages/api/.+)\.(t|j)sx?$', path):
            self.file_entry = ('http', f'next-api /{_next_api_path(path)}')
        elif lang == 'js' and (ext in ('.jsx', '.tsx', '.vue', '.svelte') or (SCREEN_PATH.search(path) and not SERVER_PATH.search(path))) \
                and not re.search(r"^\s*['\"]use server['\"]", masked, re.M):
            self.file_entry = ('screen', f'screen {os.path.splitext(os.path.basename(path))[0]}') if (ext in ('.jsx', '.tsx', '.vue', '.svelte')) else None
        elif lang == 'js' and re.search(r"^\s*['\"]use server['\"]", masked, re.M):
            self.file_entry = ('screen', f'server-action {os.path.splitext(os.path.basename(path))[0]}')
        elif lang == 'jvm' and re.search(r'class\s+\w+\s*(?:\([^)]*\))?\s*(?::|extends)\s*(?:AppCompat)?(?:Activity|Fragment|ComponentActivity|FragmentActivity)\b', masked):
            self.file_entry = ('screen', f'android {os.path.splitext(os.path.basename(path))[0]}')
        elif lang == 'dart' and re.search(r'extends\s+(State<|StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerState<|HookWidget)', masked):
            self.file_entry = ('screen', f'flutter {os.path.splitext(os.path.basename(path))[0]}')
        elif lang == 'js' and re.search(r"client\.on\(\s*['\"](messageCreate|interactionCreate|message)['\"]|bot\.(command|on|hears)\s*\(", masked):
            self.file_entry = ('bot', f'bot {os.path.basename(path)}')
        else:
            self.file_entry = None
        # 호출 자리·이름 호출
        for i, l in enumerate(lines, 1):
            fidx = self.enclosing(i)
            for rx, need, fixed, kind in calls_tbl:
                if need and not (need & self.provs):
                    continue
                if rx.search(l):
                    prov = fixed or sorted(need & self.provs)[0]
                    if prov == 'Vercel AI SDK':
                        sub = sorted(p for p in self.provs if p not in ('Vercel AI SDK', 'LangChain', 'MCP'))
                        prov = sub[0] if sub else 'Vercel AI SDK'
                    if prov == 'Spring AI' and kind == 'chat' and rx.pattern.startswith(r'\.prompt'):
                        if not re.search(r'\.(call|stream)\s*\(\s*\)', '\n'.join(lines[i - 1:i + 8])):
                            continue
                    self.sites.append(dict(cell=None, line=i, prov=prov, kind=kind, local=bool(R.LOCAL_PROV.search(prov)), rule=f'{lang}-sdk', func=fidx, kw=[]))
                    break
            m = R.JS_LC_CTOR.search(l) if lang == 'js' else None
            if m and (self.provs & {'LangChain', 'OpenAI', 'Anthropic', 'Gemini', 'Ollama'}) and any(p.startswith('@langchain') or p == 'langchain' for p in self.imports):
                prov, kind, local = R.LC_CTOR[m.group(1)]
                self.sites.append(dict(cell=None, line=i, prov=prov, kind=kind, local=local, rule='js-langchain-ctor', func=fidx, kw=[]))
            m = R.JS_PIPELINE.search(l) if lang == 'js' else None
            if m and 'Hugging Face(로컬)' in self.provs:
                self.sites.append(dict(cell=None, line=i, prov='Hugging Face(로컬)', kind=R.HF_TASK.get(m.group(1), 'model-inference'), local=True,
                                       rule='js-hf-pipeline', func=fidx, kw=[]))
            hh = None
            for sm in re.finditer(r'"([^"\n]*)"|\'([^\'\n]*)\'|`([^`]*)`', l):
                hh = R.host_hit(sm.group(0))
                if hh:
                    break
            if hh and not re.match(r'^\s*(import|package)\b', l):
                self.hosts.append(dict(cell=None, line=i, prov=hh[0], kind=hh[1], func=fidx))
            for cm in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', nostr[i - 1]):
                nm = cm.group(1)
                if nm not in JS_NOT and nm not in JVM_NOT:
                    self.calls.append(dict(name=nm, cell=None, line=i, func=fidx, main=False))
            # 기법 신호(줄 규칙은 아는 것만)
            if lang == 'js':
                if 'MCP' in self.provs and re.search(r'\bnew\s+(McpServer|Server|Client)\s*\(|\.(registerTool|tool|registerPrompt|registerResource)\s*\(', l):
                    self.tech.append(dict(tech='mcp', cell=None, line=i, strong=True, rule='js-mcp', func=fidx))
                if re.search(r'\bgenerateObject\s*\(|\bstreamObject\s*\(|\bzodResponseFormat\s*\(|response_format\s*:|responseMimeType\s*:\s*[\'"]application/json|responseSchema\s*:', l) and self.provs:
                    self.tech.append(dict(tech='structured_output', cell=None, line=i, strong=True, rule='js-structured', func=fidx))
                if re.search(r'\btools\s*:\s*[\[{]|\bfunctions\s*:\s*\[|\btool_choice\s*:|\bfunctionDeclarations\s*:', l) and self.provs - {'MCP'}:
                    self.tech.append(dict(tech='tool_calling', cell=None, line=i, strong=False, rule='js-tools-arg', func=fidx))
                if re.search(r'\.(query|search|similaritySearch|asRetriever)\s*\(', l) and self.provs & {'Pinecone', 'Chroma', 'Qdrant', 'LangChain'}:
                    self.tech.append(dict(tech='embedding_search', cell=None, line=i, strong=True, rule='js-vector', func=fidx))
                if re.search(r'\b(PromptTemplate|ChatPromptTemplate)\.from', l):
                    self.tech.append(dict(tech='prompt_template', cell=None, line=i, strong=True, rule='js-lc-prompt', func=fidx))
            if lang == 'jvm':
                if re.search(r'\bvectorStore\s*\.\s*similaritySearch\s*\(|EmbeddingStore\w*\s*\.\s*(?:findRelevant|search)\s*\(', l):
                    self.tech.append(dict(tech='embedding_search', cell=None, line=i, strong=True, rule='jvm-vector', func=fidx))
                if re.search(r'QuestionAnswerAdvisor|RetrievalAugmentationAdvisor|ContentRetriever', l) and self.provs & {'Spring AI', 'LangChain4j'}:
                    self.tech.append(dict(tech='rag', cell=None, line=i, strong=True, rule='jvm-rag-advisor', func=fidx))
                if re.search(r'\.tools\s*\(|@Tool\b|\.functions\s*\(|\.toolCallbacks\s*\(', l) and self.provs & {'Spring AI', 'LangChain4j', 'Anthropic', 'OpenAI'}:
                    self.tech.append(dict(tech='tool_calling', cell=None, line=i, strong=False, rule='jvm-tools', func=fidx))
                if re.search(r'\.entity\s*\(|BeanOutputConverter|\.outputConfig\s*\(|responseFormat\s*\(', l) and self.provs & {'Spring AI', 'LangChain4j', 'Anthropic', 'OpenAI'}:
                    self.tech.append(dict(tech='structured_output', cell=None, line=i, strong=False, rule='jvm-structured', func=fidx))

    def enclosing(self, line):
        best = None
        for fi, f in enumerate(self.funcs):
            if f['start'] <= line <= f['end']:
                if best is None or f['start'] >= self.funcs[best]['start']:
                    best = fi
        return best


def _route_path(l):
    m = re.search(r'''\.\s*(?:get|post|put|delete|patch|all)\s*\(\s*['"`]([^'"`]+)['"`]''', l)
    return m.group(1) if m else '?'


def _next_api_path(path):
    m = re.search(r'(?:app/(?:.*/)?api/(.+?)/route|pages/api/(.+))\.(t|j)sx?$', path)
    return ('api/' + (m.group(1) or m.group(2))) if m else path


# ---------------------------------------------------------------- 레포 하나
class RepoScan:
    def __init__(self, person, repo):
        self.person, self.repo = person, repo
        self.own = Own(repo)
        self.proj = root_key(repo)
        self.scans = {}            # path -> PyScan/LineScan
        self.parser = {}           # path -> 'ast'·'line-rule'·'none'
        self.raw = {}
        self.unreadable, self.parse_err, self.norule_trace, self.dep_traces = [], [], [], []
        self.reclassified = 0
        self.texts = {}
        self.kinds = {}
        self._scan()

    def _scan(self):
        r = self.repo
        cand = []
        for f in r.files:
            k, rec = real_kind(f)
            self.kinds[f['path']] = k
            if rec:
                self.reclassified += 1
            if k in ('vendor', 'generated'):
                continue
            p = f['path']
            e = ext_of(p)
            if k in ('code', 'notebook', 'test') or (k == 'config' and R.DEP_FILE.search(p)) or R.DEP_FILE.search(p):
                lim = NB_MAX if e == '.ipynb' else READ_MAX
                if (f.get('size') or 0) > lim:
                    self.unreadable.append(p)
                    continue
                if e in PY_EXT + JS_EXT + JVM_EXT + DART_EXT + NORULE_EXT + ('.ipynb',) or R.DEP_FILE.search(p):
                    cand.append(f)
        self.texts = read_blobs(r, cand)
        for f in cand:
            p = f['path']
            t = self.texts.get(p)
            if t is None:
                self.unreadable.append(p)
                continue
            e = ext_of(p)
            if R.DEP_FILE.search(p):
                for i, l in enumerate(t.split('\n'), 1):
                    lm = re.sub(r'(^|\s)#.*$', '', l) if not p.endswith('.json') else l
                    m = R.DEP_AI.search(lm)
                    if m:
                        self.dep_traces.append(dict(path=p, line=i, name=m.group(1).lower(), ml=False))
                    m2 = R.DEP_ML.search(lm)
                    if m2 and not (p.endswith('package.json') and m2.group(1) in ('datasets', 'lightning')):
                        self.dep_traces.append(dict(path=p, line=i, name=m2.group(1).lower(), ml=True))
                if self.kinds[p] not in ('code', 'notebook', 'test'):
                    continue
            if self.kinds[p] == 'test':
                continue
            if not R.KW_AI.search(t) and not re.search(r'(?i)\b(train_test_split|cross_val|GridSearch|joblib|pickle|fit\(|mcp|response_format|tools)', t):
                continue
            if e in PY_EXT or e == '.ipynb':
                s = scan_python(p, t, e == '.ipynb')
                if s is None:
                    self.parse_err.append(p)
                    continue
                if s.err:
                    self.parse_err.append(p)
                self.scans[p] = s
                self.parser[p] = 'ast(py%d.%d)' % sys.version_info[:2]
                if e == '.ipynb':
                    self.raw[p] = nb_raw_ranges(t)
            elif e in JS_EXT:
                self.scans[p] = LineScan(p, t, 'js')
                self.parser[p] = 'line-rule'
            elif e in JVM_EXT:
                self.scans[p] = LineScan(p, t, 'jvm')
                self.parser[p] = 'line-rule'
            elif e in DART_EXT:
                self.scans[p] = LineScan(p, t, 'dart')
                self.parser[p] = 'line-rule'
            elif e in NORULE_EXT and R.KW_AI.search(t):
                lines = [i for i, l in enumerate(t.split('\n'), 1) if R.KW_AI.search(l)]
                mine = [i for i in lines if self.own.is_mine(p, i, reblame=True)]
                if mine:
                    self.norule_trace.append(dict(path=p, lines=mine[:20]))

    # -- 위치 → 내 줄?
    def mine(self, path, cell, line):
        if cell is not None:
            return self.own.is_mine(path, 0) if self.own.lines(path)[0] != 'blame' else None
        return self.own.is_mine(path, line, reblame=True)

    def loc(self, path, cell, line):
        """근거 위치: (경로(노트북은 '경로#셀'), 줄, S5 자료용 원본 줄 범위)"""
        if cell is None:
            return path, line, (max(1, line - 40), line + 40)
        rr = self.raw.get(path, {}).get(cell)
        if rr:
            a, b = rr
            raw_line = min(b, a + max(0, line - 1))
            return f'{path}#{cell}', line, (max(1, a - 2), min(b + 2, a + 200))
        return f'{path}#{cell}', line, (1, 200)


# ---------------------------------------------------------------- 사람 하나
def extract(person):
    t0 = time.time()
    data = dict(category=CAT, pid=person.pid, variables={}, s5_targets=[], definition_choices=[], stats={})
    reps = []
    for repo in person.repos:
        if repo.meta.get('error') or not repo.refs:
            reps.append((repo, None))
            continue
        reps.append((repo, RepoScan(person, repo)))
    inst = collections.defaultdict(list)
    evid = collections.defaultdict(list)
    targets = []
    tcount = collections.Counter()

    def add_inst(var, rs, path, line, what, status):
        if len(inst[var]) < MAX_INST:
            inst[var].append(dict(repo=rs.repo.key, path=path, line=line, what=what, status=status))

    def add_ev(var, rs, path=None, line=None, sha=None, rule=None, note=None):
        if len(evid[var]) < 60:
            evid[var].append(L.evidence(rs.repo, path=path, line=line, sha=sha, rule=rule, note=note))

    def target(var, rs, template, files, commits=None, text=None, rule_result=None, trace='has_trace', priority=5, group=None, stop_rule=None):
        tcount[var] += 1
        tid = f'{person.pid}.{KEY}.{var}.{tcount[var]}'
        t = dict(target_id=tid, var=var, repo=rs.repo.key, template=template,
                 material=dict(files=[dict(path=a, start=b, end=c) for a, b, c in files], commits=list(commits or [])),
                 rule_result=rule_result, trace=trace, priority=priority)
        if text:
            t['material']['text'] = text[:600]
        if group:
            t['group'] = group
            t['stop_rule'] = stop_rule or 'first_yes'
        targets.append(t)
        return tid

    # ======================= 1) AI 연동 수
    pairs_B = {}            # (prov, kind) -> first evidence
    provs_A = {}
    pairs_C = {}            # (proj, prov, kind, func) -> ev
    pairs_B_nolocal = {}
    by_repo_int = {}
    site_list = []          # (rs, path, scan, site, mine)
    unresolved_int = []     # S5 후보
    for repo, rs in reps:
        if rs is None:
            continue
        rp = set()
        for path, sc in rs.scans.items():
            exm = is_example(path)
            imp_ai = False
            if isinstance(sc, PyScan):
                imp_ai = bool(sc.imports & {'openai', 'anthropic', 'google', 'vertexai', 'langchain', 'langchain_openai', 'langchain_community',
                                            'langchain_core', 'llama_index', 'ollama', 'transformers', 'sentence_transformers', 'huggingface_hub',
                                            'cohere', 'mistralai', 'groq', 'together', 'replicate', 'whisper', 'faster_whisper', 'ultralytics',
                                            'mediapipe', 'langchain_google_genai', 'langchain_anthropic', 'langchain_ollama', 'langchain_huggingface',
                                            'langchain_upstage', 'langchain_groq', 'elevenlabs', 'easyocr', 'deepface'})
                if 'google' in sc.imports and not any(v.startswith(('google.generativeai', 'google.genai', 'google.cloud.vision', 'google.cloud.speech',
                                                                     'google.cloud.texttospeech', 'google.cloud.language')) for v in sc.alias.values()):
                    imp_ai = imp_ai and bool(sc.imports - {'google'} & {'openai', 'anthropic', 'langchain'})
            else:
                imp_ai = bool(sc.provs - {'MCP', 'Pinecone', 'Chroma', 'Qdrant'})
            found_mine = False
            all_sites = list(sc.sites) + ([dict(h, rule='ai-host-string', local=(h['prov'] == 'Ollama'), kw=[]) for h in sc.hosts] if sc.http_lib or isinstance(sc, LineScan) else [])
            for s in all_sites:
                if s.get('unused'):
                    lp, ln, rng = rs.loc(path, s['cell'], s['line'])
                    add_inst('integrations', rs, lp, ln, f"{s['prov']}/{s['kind']} 생성만(안 쓰임)", 'excluded')
                    continue
                mine = rs.mine(path, s['cell'], s['line'])
                lp, ln, rng = rs.loc(path, s['cell'], s['line'])
                if exm:
                    add_inst('integrations', rs, lp, ln, f"{s['prov']}/{s['kind']} 예시 경로", 'excluded')
                    continue
                if mine is None:
                    unresolved_int.append((rs, path, s, rng, 'own-unknown'))
                    add_inst('integrations', rs, lp, ln, f"{s['prov']}/{s['kind']} 내 줄 모름", 's5')
                    continue
                if not mine:
                    add_inst('integrations', rs, lp, ln, f"{s['prov']}/{s['kind']} 남의 줄", 'excluded')
                    continue
                found_mine = True
                fn = sc.funcs[s['func']]['name'] if s.get('func') is not None and s['func'] < len(sc.funcs) else '<module>'
                key = (s['prov'], s['kind'])
                ev = dict(repo=rs.repo.key, path=lp, line=ln, rule=f"ai.integrations.{s['rule']}@1")
                pairs_B.setdefault(key, ev)
                provs_A.setdefault(s['prov'], ev)
                pairs_C.setdefault((rs.proj, s['prov'], s['kind'], path, fn), ev)
                if not s.get('local'):
                    pairs_B_nolocal.setdefault(key, ev)
                rp.add(key)
                add_inst('integrations', rs, lp, ln, f"{s['prov']}/{s['kind']} ({s['rule']})", 'counted')
                if len(evid['integrations']) < 60:
                    add_ev('integrations', rs, path=lp, line=ln, rule=f"ai.integrations.{s['rule']}@1", note=f"{s['prov']}/{s['kind']}")
                site_list.append((rs, path, sc, s, fn))
            # 흔적: AI SDK import는 있는데 내 호출을 못 찾음
            if imp_ai and not found_mine:
                own_ai_lines = []
                txt = rs.texts.get(path, '')
                for i, l in enumerate(txt.split('\n'), 1):
                    if R.KW_AI.search(l) and rs.own.is_mine(path, i, reblame=True):
                        own_ai_lines.append(i)
                if own_ai_lines or (ext_of(path) == '.ipynb' and rs.own.has_mine(path)):
                    first = own_ai_lines[0] if own_ai_lines else 1
                    unresolved_int.append((rs, path, None, (max(1, first - 30), first + 120), 'import-no-call'))
        for p in rs.parse_err:
            t = rs.texts.get(p, '')
            if R.KW_AI.search(t) and rs.own.has_mine(p, reblame=True):
                unresolved_int.append((rs, p, None, (1, 200), 'parse-error'))
        for nt in rs.norule_trace:
            unresolved_int.append((rs, nt['path'], None, (max(1, nt['lines'][0] - 30), nt['lines'][0] + 120), 'no-rule-language'))
        by_repo_int[rs.repo.key] = len(rp)
    # 의존성만 있는 레포(코드에 AI 흔적 없음)
    for repo, rs in reps:
        if rs is None:
            continue
        ai_deps = [d for d in rs.dep_traces if not d['ml']]
        if ai_deps and not by_repo_int.get(rs.repo.key) and not any(u[0] is rs for u in unresolved_int):
            mine_code = sorted(((f.get('my_lines') or 0), f['path']) for f in rs.repo.files if rs.kinds.get(f['path']) == 'code')
            if mine_code and mine_code[-1][0] > 0:
                d = ai_deps[0]
                unresolved_int.append((rs, d['path'], None, (max(1, d['line'] - 20), d['line'] + 20), 'dependency-only:' + mine_code[-1][1]))
    seen_t = set()
    for rs, path, s, rng, why in sorted(unresolved_int, key=lambda x: (0 if x[4] == 'own-unknown' else 1, x[1])):
        k = (rs.repo.key, path)
        if k in seen_t or tcount['integrations'] >= CAP_INT:
            continue
        seen_t.add(k)
        files = [(path, rng[0], rng[1])]
        if why.startswith('dependency-only:'):
            top = why.split(':', 1)[1]
            files.append((top, 1, 150))
        target('integrations', rs, 'ai.integration', files, rule_result=dict(reason=why, rule_value=0), priority=1 if why != 'dependency-only' else 3)
    n_has_int = tcount['integrations']
    val_B = len(pairs_B)
    data['variables']['ai.integrations'] = dict(
        name='AI 연동 수', role='count', value=val_B if (val_B or not n_has_int) else None,
        state=('value_rule' if val_B else ('zero_unused' if not n_has_int else None)), unit='개((제공자, API 종류) 쌍)',
        by_repo=by_repo_int, instances=inst['integrations'], evidence=evid['integrations'],
        definition='「Claude 정의」(B-37 후보 B): 내 줄(blame, 테스트·예시·생성 경로 제외)에서 AI 모델·서비스를 실제로 부르는 곳의 서로 다른 (제공자, API 종류) 쌍 수, '
                   '레포를 합쳐 한 번. 호출 = SDK 호출(풀이한 별칭·인스턴스 따라감), LangChain·LlamaIndex 생성자는 그 이름이 다시 쓰일 때만, AI 주소 문자열은 그 파일에 HTTP 호출이 있을 때만. '
                   '로컬 모델(Hugging Face·Whisper·YOLO·MediaPipe·Ollama·TFLite 등)도 넣는다. 의존성·import만이면 X(「문서」 규칙 8). ML 학습 프레임워크(torch·sklearn 등)는 연동이 아니라 기법.',
        notes=f'S5 대상 {n_has_int}건(흔적만: import는 있는데 호출 못 찾음·구문 오류·규칙 없는 언어·의존성만). 대기 중이면 값은 규칙 몫만.',
        parts=dict(providers=sorted(provs_A), pairs=sorted(f'{a}/{b}' for a, b in pairs_B)), s5_waiting=n_has_int)
    alt_int = dict(A_providers=len(provs_A), B_pairs=val_B, B_pairs_no_local=len(pairs_B_nolocal), C_endpoint_x_function=len(pairs_C))

    # ======================= 2) AI 기법 수
    tech_hits = collections.defaultdict(list)     # tech -> [(rs, path, cell, line, strong, rule)]
    for repo, rs in reps:
        if rs is None:
            continue
        for path, sc in rs.scans.items():
            if is_example(path):
                continue
            tl = sc.tech
            fnames = {}
            # 파일 단위 조합 신호
            has = collections.defaultdict(list)
            for x in tl:
                has[x['tech']].append(x)
            if has.get('_backward') and has.get('_optstep'):
                x = has['_backward'][0]
                tl = tl + [dict(tech='model_training', cell=x['cell'], line=x['line'], strong=True, rule='torch-loop', func=x['func'])]
                has['model_training'].append(tl[-1])
            trained = bool(has.get('model_training')) or bool(has.get('_trainer'))
            if has.get('_pretrained') and trained:
                x = has['_pretrained'][0]
                causal = any(y.get('causal') for y in has['_pretrained'])
                tl = tl + [dict(tech='transfer_learning', cell=x['cell'], line=x['line'], strong=True, rule='pretrained+train', func=x['func'])]
                if causal or any(y.get('trl') for y in has.get('_trainer', [])):
                    tl = tl + [dict(tech='fine_tuning', cell=x['cell'], line=x['line'], strong=True, rule='causal-lm+trainer', func=x['func'])]
            if has.get('_pretrained_train'):
                x = has['_pretrained_train'][0]
                tl = tl + [dict(tech='transfer_learning', cell=x['cell'], line=x['line'], strong=False, rule='yolo-train(가중치 확인 필요)', func=x['func'])]
            entries = sc.entries or getattr(sc, 'entry_for', None) or (isinstance(sc, PyScan) and (sc.streamlit or sc.gradio))
            if (has.get('_model_load') or has.get('_predict')) and entries and not trained:
                x = (has.get('_model_load') or has.get('_predict'))[0]
                tl = tl + [dict(tech='serving', cell=x['cell'], line=x['line'], strong=True, rule='model-load+entry', func=x['func'])]
            elif has.get('_model_load') and isinstance(sc, PyScan) and (sc.imports & {'flask', 'fastapi', 'django', 'streamlit', 'gradio'}):
                x = has['_model_load'][0]
                tl = tl + [dict(tech='serving', cell=x['cell'], line=x['line'], strong=False, rule='model-load+web-import', func=x['func'])]
            # RAG 약한 신호: 같은 파일에 벡터 검색 + LLM 생성
            vec = has.get('embedding_search')
            gen = [s for s in sc.sites if s['kind'] == 'chat']
            if vec and gen and not has.get('rag'):
                tl = tl + [dict(tech='rag', cell=vec[0]['cell'], line=vec[0]['line'], strong=False, rule='vector+llm-same-file', func=vec[0]['func'])]
            # 에이전트 약한 신호: tool_calls를 반복문 안에서 다룸(Python)
            if isinstance(sc, PyScan) and has.get('tool_calling') and not has.get('agent'):
                txt = rs.texts.get(path, '')
                if re.search(r'(?s)(while|for)\b[^\n]*:\s*\n.{0,3000}?(tool_calls|stop_reason\s*==\s*[\'"]tool_use|function_call)', txt):
                    x = has['tool_calling'][0]
                    tl = tl + [dict(tech='agent', cell=x['cell'], line=x['line'], strong=False, rule='tool-loop', func=x['func'])]
            # 프롬프트 체인 약한 신호: 한 함수 안 LLM 호출 2곳 이상
            byf = collections.Counter(s.get('func') for s in gen if s.get('func') is not None)
            for fidx, n in byf.items():
                if n >= 2 and not has.get('prompt_chain'):
                    s0 = next(s for s in gen if s.get('func') == fidx)
                    tl = tl + [dict(tech='prompt_chain', cell=s0['cell'], line=s0['line'], strong=False, rule='2+llm-calls-one-func', func=fidx)]
                    break
            for x in tl:
                if x['tech'].startswith('_'):
                    continue
                mine = rs.mine(path, x['cell'], x['line'])
                lp, ln, rng = rs.loc(path, x['cell'], x['line'])
                tech_hits[x['tech']].append((rs, path, x, mine, lp, ln, rng))
        # 프롬프트 파일(내 커밋이 바꾼 것, AI 연동이 있는 레포)
        if by_repo_int.get(rs.repo.key):
            for f in rs.repo.files:
                if PROMPT_FILE.search(f['path']) and rs.own.touch.get(f['path'], (0, 0))[0] and not is_example(f['path']):
                    tech_hits['prompt_template'].append((rs, f['path'], dict(tech='prompt_template', cell=None, line=1, strong=False, rule='prompt-file', func=None),
                                                         True, f['path'], 1, (1, 120)))
        for f in rs.repo.files:
            if re.search(r'(^|/)dvc\.yaml$|\.dvc$', f['path']) and rs.own.touch.get(f['path'], (0, 0))[0]:
                tech_hits['data_versioning'].append((rs, f['path'], dict(tech='data_versioning', cell=None, line=1, strong=True, rule='dvc-file', func=None),
                                                     True, f['path'], 1, (1, 60)))
    ml_trace = []
    for repo, rs in reps:
        if rs is None:
            continue
        mine_hits = {h[1] for t_, hs in tech_hits.items() for h in hs if h[0] is rs and h[3]}
        if mine_hits:
            continue
        best = None
        for path, txt in rs.texts.items():
            if rs.kinds.get(path) not in ('code', 'notebook') or is_example(path) or ext_of(path) not in PY_EXT + ('.ipynb',) + JS_EXT + JVM_EXT:
                continue
            ls = [i for i, l in enumerate(txt.split('\n'), 1) if R.KW_ML.search(l)]
            if not ls:
                continue
            if ext_of(path) == '.ipynb':
                ok = rs.own.has_mine(path)
                n = len(ls) if ok else 0
                first = ls[0]
            else:
                mine = [i for i in ls if rs.own.is_mine(path, i, reblame=True)]
                n, first = len(mine), (mine[0] if mine else 0)
            if n and (best is None or n > best[0]):
                best = (n, path, first)
        if best:
            ml_trace.append((rs, best[1], best[2]))
    tech_rule = {}
    tech_by_repo = collections.defaultdict(set)
    weak_targets = collections.defaultdict(list)
    for tech, hits in tech_hits.items():
        for rs, path, x, mine, lp, ln, rng in hits:
            if mine is False:
                add_inst('techniques', rs, lp, ln, f'{tech} 남의 줄 ({x["rule"]})', 'excluded')
                continue
            if x['strong'] and mine:
                if tech not in tech_rule:
                    tech_rule[tech] = dict(repo=rs.repo.key, path=lp, line=ln, rule=f"ai.techniques.{x['rule']}@1")
                    add_ev('techniques', rs, path=lp, line=ln, rule=f"ai.techniques.{x['rule']}@1", note=tech)
                tech_by_repo[rs.repo.key].add(tech)
                add_inst('techniques', rs, lp, ln, f'{tech} ({x["rule"]})', 'counted')
            else:
                weak_targets[tech].append((rs, path, x, lp, ln, rng, 'own-unknown' if mine is None else 'weak-signal'))
                add_inst('techniques', rs, lp, ln, f'{tech} 약한 신호 ({x["rule"]})', 's5')
    for tech, ws in weak_targets.items():
        if tech in tech_rule:
            continue           # 이미 규칙으로 확정(사람 단위 한 번)
        seen = set()
        n = 0
        for rs, path, x, lp, ln, rng, why in ws:
            k = (rs.repo.key, path)
            if k in seen or n >= CAP_TECH_PER:
                continue
            seen.add(k)
            n += 1
            target('techniques', rs, f'ai.technique.{tech}', [(path, rng[0], rng[1])], rule_result=dict(technique=tech, signal=x['rule'], reason=why),
                   priority=n, group=f'TECH_{tech}', stop_rule='first_yes')
    for rs, path, first in ml_trace[:4]:
        target('techniques', rs, 'ai.technique.any', [(path, max(1, first - 30), first + 170)], rule_result=dict(technique='any', reason='ml-keywords-no-signal'),
               priority=7)
    n_llm = sum(1 for t in tech_rule if t in R.TECH_LLM)
    n_ml = sum(1 for t in tech_rule if t in R.TECH_ML)
    n_has_tech = tcount['techniques']
    tval = n_llm + n_ml
    data['variables']['ai.techniques'] = dict(
        name='AI 기법 수', role='count', value=tval if (tval or not n_has_tech) else None,
        state=('value_rule' if tval else ('zero_unused' if not n_has_tech else None)), unit='개(목록 항목)',
        parts=dict(llm=n_llm, ml=n_ml, llm_list=sorted(t for t in tech_rule if t in R.TECH_LLM), ml_list=sorted(t for t in tech_rule if t in R.TECH_ML)),
        by_repo={k: len(v) for k, v in tech_by_repo.items()}, instances=inst['techniques'], evidence=evid['techniques'],
        definition='「Claude 정의」(B-38): 기법 1개 = 목록 항목 하나를 내 줄에서 실제로 한 근거가 1곳 이상(사람 단위 한 번). '
                   'LLM 목록 10: ' + '·'.join(R.TECH_NAME[t] for t in R.TECH_LLM) + ' / ML 목록 10: ' + '·'.join(R.TECH_NAME[t] for t in R.TECH_ML) +
                   '. 규칙은 확실한 신호(라이브러리 호출·호출 인자)만 확정하고, 조합으로만 보이는 것(벡터 검색+생성=RAG, 도구 루프=에이전트, 한 함수의 LLM 2회=체인, '
                   '프롬프트 파일, 이름을 못 푼 fit 등)은 S5(기법마다 첫 yes에서 멈춤). parts.llm·parts.ml을 따로 단계로 바꿔 높은 쪽을 쓴다(B-38 「제안」).',
        notes=f'S5 대상 {n_has_tech}건(기법 {len([t for t in weak_targets if t not in tech_rule])}개 후보, 기법마다 최대 {CAP_TECH_PER}건, first_yes).',
        s5_waiting=n_has_tech)
    alt_tech = dict(full_llm_plus_ml=tval, llm_only=n_llm, ml_only=n_ml, max_stage_reading='S6(LLM·ML 각각 단계 → 높은 쪽)',
                    narrow_list=sum(1 for t in tech_rule if t in R.TECH_NARROW))

    # ======================= 3) AI 기능 수
    feats_A, feats_C, feats_S = {}, {}, {}
    unresolved_feat = []
    by_repo_feat = collections.Counter()
    for repo, rs in reps:
        if rs is None:
            continue
        mysites = [x for x in site_list if x[0] is rs]
        if not mysites:
            continue
        # 이름 → 정의들, 호출 목록(같은 언어 계열)
        defs = collections.defaultdict(list)
        callers = collections.defaultdict(list)
        for path, sc in rs.scans.items():
            fam = 'py' if isinstance(sc, PyScan) else sc.lang
            for fi, f in enumerate(sc.funcs):
                defs[(fam, f['name'])].append((path, fi))
            for c in sc.calls:
                callers[(fam, c['name'])].append((path, c['func'], c.get('main'), c['line']))
        entry_for = collections.defaultdict(dict)
        for path, sc in rs.scans.items():
            fam = 'py' if isinstance(sc, PyScan) else sc.lang
            for n, v in getattr(sc, 'entry_for', {}).items():
                entry_for[fam][n] = v
        for rs_, path, sc, s, fn in mysites:
            fam = 'py' if isinstance(sc, PyScan) else sc.lang
            found, roots = set(), set()
            seen = set()
            q = [(path, s.get('func'), 0)]
            while q:
                p, fi, d = q.pop(0)
                if (p, fi) in seen:
                    continue
                seen.add((p, fi))
                scx = rs.scans.get(p)
                if scx is None:
                    continue
                if fi is None:
                    # 모듈 수준
                    if isinstance(scx, PyScan):
                        if scx.streamlit:
                            found.add(('screen', f'streamlit {os.path.basename(p)}'))
                        elif scx.gradio:
                            found.add(('screen', f'gradio {os.path.basename(p)}'))
                        elif ext_of(p) == '.ipynb':
                            roots.add(('notebook', p))
                        elif scx.module_main or not scx.has_defs:
                            found.add(('cli' if scx.cli_iface else 'script', f'script {os.path.basename(p)}'))
                        else:
                            roots.add(('module', p))
                    else:
                        if scx.file_entry:
                            found.add(scx.file_entry)
                        else:
                            roots.add(('module', p))
                    continue
                f = scx.funcs[fi]
                for e in scx.entries:
                    if e.get('func') == fi:
                        found.add((e['kind'], e['key']))
                if f['name'] in entry_for[fam]:
                    found.add(entry_for[fam][f['name']])
                if isinstance(scx, LineScan) and scx.file_entry and scx.file_entry[0] == 'screen':
                    found.add(scx.file_entry)
                if found and d > 0:
                    pass
                cs = [c for c in callers.get((fam, f['name']), []) if not (c[0] == p and c[1] == fi)]
                if len(defs.get((fam, f['name']), [])) > 1 or f['name'].lower() in GENERIC:
                    stem = re.escape(os.path.splitext(os.path.basename(p))[0])
                    cs = [c for c in cs if c[0] == p or re.search(r'\b' + stem + r'\b', rs.texts.get(c[0], ''))]
                if not cs:
                    roots.add((p, f['name']))
                if d >= DEPTH:
                    continue
                for cp, cfi, cmain, cline in cs[:40]:
                    if cmain:
                        cps = rs.scans.get(cp)
                        found.add(('cli' if (cps is not None and getattr(cps, 'cli_iface', False)) else 'script', f'main {os.path.basename(cp)}'))
                        continue
                    q.append((cp, cfi, d + 1))
            lp, ln, rng = rs.loc(path, s['cell'], s['line'])
            for kind, key in found:
                feats_S.setdefault((rs.proj, kind, key), 1)
            real = {(k_, v_) for k_, v_ in found if k_ != 'script'}
            if found and not real:
                for kind, key in found:
                    add_inst('features', rs, lp, ln, f'스크립트만(CLI 인터페이스 없음): {key} ← {s["prov"]}/{s["kind"]}', 'excluded')
            if real:
                for kind, key in real:
                    fk = (rs.proj, kind, key)
                    if fk not in feats_A:
                        feats_A[fk] = dict(repo=rs.repo.key, path=lp, line=ln, rule='ai.features.entry-trace@1', entry=f'{kind}: {key}')
                        by_repo_feat[rs.repo.key] += 1
                        add_inst('features', rs, lp, ln, f'{kind}: {key} ← {s["prov"]}/{s["kind"]}', 'counted')
                        add_ev('features', rs, path=lp, line=ln, rule='ai.features.entry-trace@1', note=f'{kind}: {key}')
            elif not found:
                unresolved_feat.append((rs, path, s, fn, lp, ln, rng))
                add_inst('features', rs, lp, ln, f'진입점 못 찾음 ← {s["prov"]}/{s["kind"]} in {fn}', 's5')
            for r_ in (roots or {(path, fn)}):
                feats_C.setdefault((rs.proj,) + tuple(r_), 1)
    seenf = set()
    for rs, path, s, fn, lp, ln, rng in unresolved_feat:
        k = (rs.repo.key, path, fn)
        if k in seenf or tcount['features'] >= CAP_FEAT:
            continue
        seenf.add(k)
        sc = rs.scans[path]
        if s.get('func') is not None and s['func'] < len(sc.funcs) and s['cell'] is None:
            f = sc.funcs[s['func']]
            a, b = max(1, f['start'] - 5), min(f['end'] + 5, f['start'] + 250)
        else:
            a, b = rng
        target('features', rs, 'ai.feature', [(path, a, b)], rule_result=dict(ai_call=f"{s['prov']}/{s['kind']}", function=fn, reason='entry-not-found'),
               priority=2)
    n_has_feat = tcount['features']
    fval = len(feats_A)
    data['variables']['ai.features'] = dict(
        name='AI 기능 수', role='count', value=fval if (fval or not n_has_feat) else None,
        state=('value_rule' if fval else ('zero_unused' if not n_has_feat else None)), unit='개(사용자 진입점)',
        by_repo=dict(by_repo_feat), instances=inst['features'], evidence=evid['features'],
        definition='「Claude 정의」(B-39 후보 A): 사용자에게 보이는 진입점(HTTP API·화면·CLI·봇 명령) 하나가 AI 연동 수에 센 내 AI 호출의 결과를 쓰면 1개. '
                   '규칙이 AI 호출의 감싼 함수에서 이름 호출 그래프를 최대 4단계 따라가 진입점(FastAPI·Flask·Django·DRF·Express·NestJS·Next.js API·Spring 매핑·'
                   'Streamlit·Gradio·봇 핸들러·CLI 인터페이스(argparse·click·typer·fire·sys.argv)가 있는 스크립트·React/Vue 화면 파일·Android·Compose·Flutter 화면)을 찾는다. '
                   'CLI 인터페이스 없는 __main__·함수 없는 스크립트(실험·일회성)는 뺀다(대안 A_plus_plain_scripts). (프로젝트, 진입점)으로 한 번. '
                   '노트북은 진입점이 아니다. 못 찾으면 S5(호출 1개 = 대상 1개).',
        notes=f'S5 대상 {n_has_feat}건(진입점 못 찾음). 같은 호출이 연동·기능 둘 다에 든다(B-60 같은 근거 허용).', s5_waiting=n_has_feat)
    alt_feat = dict(A_entrypoints=fval, A_plus_plain_scripts=len(feats_S),
                    B_llm_grouped='N/A(S5로만 잼, 이번 실행 밖)', C_top_functions=len(feats_C))

    # ======================= 4) 검증된 AI PR 수
    pr_counts = dict(A1=0, A2='N/A', N1=0, AN1=0)
    pr_by_repo = {}
    pr_pending = 0
    login = (person.login or '').lower()
    ai_files_by_repo = {}
    for repo, rs in reps:
        if rs is None:
            continue
        ai_files = {x[1] for x in site_list if x[0] is rs}
        for tech, hits in tech_hits.items():
            for h in hits:
                if h[0] is rs:
                    ai_files.add(h[1])
        ai_files |= {f['path'] for f in rs.repo.files if PROMPT_FILE.search(f['path'])}
        ai_files_by_repo[rs.repo.key] = ai_files
    for repo, rs in reps:
        if rs is None or not rs.repo.prs:
            continue
        reach = reachable(rs.repo)
        commits_by_pr = collections.defaultdict(list)
        for c in rs.repo.commits:
            if c.get('pr'):
                commits_by_pr[c['pr']].append(c)
        cnt = collections.Counter()
        for pr in rs.repo.prs:
            user = (pr.get('user') or '').lower()
            bot = bool(R.AI_BOT_USER.match(user))
            self_auth = user == login
            merged = bool(pr.get('merged_at'))
            on_branch = bool(pr.get('merge_commit_sha')) and pr['merge_commit_sha'] in reach
            body = (pr.get('body') or '') + '\n' + (pr.get('title') or '')
            cs = commits_by_pr.get(pr['number'], [])
            strong = bool(R.GEN_MARK.search(body)) or bot or any(c['own'] and (c['ai_coauthor'] or R.TRAILER_AI.search(c['body'] or '') or R.GEN_MARK.search(c['body'] or ''))
                                                                 for c in cs)
            weak = (not strong) and bool(R.WEAK_AI_TOOL.search(body))
            ai_feat = any(f['path'] in ai_files_by_repo.get(rs.repo.key, set()) for c in cs if c['own'] for f in c['files'])
            ok_auth = self_auth or (bot and merged)
            if not (merged and on_branch and ok_auth):
                if strong and len(inst['verified_prs']) < MAX_INST:
                    add_inst('verified_prs', rs, f'pr:#{pr["number"]}', None, f"AI 표시 있음, 제외: {'머지 안 됨' if not merged else ('분석 브랜치 밖' if not on_branch else '작성자 다름')}", 'excluded')
                continue
            if strong:
                cnt['A1'] += 1
                add_inst('verified_prs', rs, f'pr:#{pr["number"]}', None, 'AI 생성 표시(본문·꼬리표·봇) + 머지 + 분석 브랜치 + 작성자 본인', 'counted')
                if len(evid['verified_prs']) < 60:
                    evid['verified_prs'].append(dict(repo=rs.repo.key, rule='ai.verified_prs.marker+merged@1', pr=pr['number'],
                                                     sha=(pr.get('merge_commit_sha') or '')[:12]))
            elif weak and tcount['verified_prs'] < CAP_PR:
                sha = cs[0]['sha'] if cs else None
                if sha:
                    target('verified_prs', rs, 'ai.pr', [], commits=[sha], rule_result=dict(pr=pr['number'], reason='weak-ai-mention', merged=True), priority=4)
                    add_inst('verified_prs', rs, f'pr:#{pr["number"]}', None, 'AI 도구 이름만 보임(S5)', 's5')
            if ai_feat:
                cnt['N1'] += 1
            if strong or ai_feat:
                cnt['AN1'] += 1
        pr_by_repo[rs.repo.key] = cnt['A1']
        for k in ('A1', 'N1', 'AN1'):
            pr_counts[k] += cnt[k]
    n_has_pr = tcount['verified_prs']
    any_prs = any(rs is not None and rs.repo.prs for _, rs in reps)
    data['variables']['ai.verified_prs'] = dict(
        name='검증된 AI PR 수', role='bonus_count', value=pr_counts['A1'],
        state='value_rule' if pr_counts['A1'] else ('zero_unused' if not n_has_pr else 'value_rule'), unit='개(PR)',
        by_repo=pr_by_repo, instances=inst['verified_prs'], evidence=evid['verified_prs'],
        definition='「Claude 정의」(B-40 (가)+①): AI 코딩 도구로 만든 PR(본문·제목의 생성 표시, PR 안 내 커밋의 AI 공동 작성자 꼬리표·생성 표시, AI 봇이 연 PR) 중 '
                   '머지됐고 머지 커밋이 분석 브랜치에 있으며 작성자가 대상 계정(봇 PR은 머지된 것)인 PR 수. 리뷰 승인(②)은 색인에 없어 N/A. '
                   'AI 도구 이름만 적힌 PR은 S5.',
        notes=f'PR 기록이 있는 레포 {sum(1 for _, rs in reps if rs is not None and rs.repo.prs)}개. PR 없이 바로 올리는 레포는 늘 0. S5 대상 {n_has_pr}건.' +
              ('' if any_prs else ' PR 0개 → 0(안 씀).'),
        s5_waiting=n_has_pr)
    alt_pr = {'(가)+① AI 생성 PR·머지': pr_counts['A1'], '(나)+① AI 파일 PR·머지': pr_counts['N1'], '(가 또는 나)+①': pr_counts['AN1'],
              '(가)+② 승인 리뷰': 'N/A(색인에 리뷰 없음)'}

    # ======================= 5) AI 도구 흔적 T
    trace_A, trace_B = [], []
    weak_tool = []
    gen_cfg = 0
    for repo, rs in reps:
        if rs is None:
            continue
        own_emails = set()
        rc, out = L.git(rs.repo.dir, 'log', '--no-merges', '--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce', *[x['ref'] for x in rs.repo.refs], timeout=300)
        rows = [l.split('\x1f') for l in out.decode('utf-8', 'replace').splitlines()] if rc == 0 else []
        own_set = rs.own.own_shas
        for row in rows:
            if len(row) == 5 and row[0] in own_set:
                own_emails.add(row[2].lower())
        for row in rows:
            if len(row) == 5 and row[0] not in own_set and R.AI_AUTHOR.search(row[1] + ' ' + row[2]) and row[4].lower() in own_emails:
                trace_B.append((rs, row[0]))
        # 설정 파일(내 커밋이 넣거나 바꿈, 기록 전체)
        cfg_paths = collections.OrderedDict()
        for c in rs.repo.commits:
            if not c['own']:
                continue
            for f in c['files']:
                if R.AI_CFG.search(f['path']) and not is_example(f['path']):
                    cfg_paths.setdefault(f['path'], c['sha'])
        for p, sha in cfg_paths.items():
            t = rs.repo.text(p) if rs.repo.file(p) else None
            if t is not None and R.GEN_FINGERPRINT.search(t):
                gen_cfg += 1
                add_inst('tool_trace', rs, p, None, 'AI 설정 파일이지만 생성기 지문(Next.js 등) → 제외', 'excluded')
                weak_tool.append((rs, p, sha, 'generator-fingerprint'))
                continue
            if t is not None and not re.sub(r'<!--.*?-->', '', t, flags=re.S).strip():
                add_inst('tool_trace', rs, p, None, 'AI 설정 파일이 비어 있음', 'excluded')
                continue
            trace_A.append((rs, p, sha, 'ai-config-file'))
            add_inst('tool_trace', rs, p, None, 'AI 설정 파일(내 커밋)', 'counted')
        n_tr = 0
        for c in rs.repo.commits:
            if c['own'] and (c['ai_coauthor'] or R.TRAILER_AI.search(c['body'] or '')):
                n_tr += 1
                if n_tr <= 3:
                    trace_A.append((rs, None, c['sha'], 'ai-coauthor-trailer'))
                    add_inst('tool_trace', rs, f'sha:{c["sha"][:8]}', None, 'AI 공동 작성자 꼬리표(내 커밋)', 'counted')
            elif c['own'] and R.GEN_MARK.search((c['subject'] or '') + '\n' + (c['body'] or '')):
                trace_A.append((rs, None, c['sha'], 'generated-marker'))
            elif c['own'] and R.WEAK_AI_TOOL.search(c['subject'] or ''):
                weak_tool.append((rs, None, c['sha'], 'commit-mentions-ai-tool'))
        for pr in rs.repo.prs:
            if (pr.get('user') or '').lower() == login and R.GEN_MARK.search(pr.get('body') or ''):
                trace_A.append((rs, None, (pr.get('merge_commit_sha') or ''), f'pr-generated-marker #{pr["number"]}'))
                break
        # 남이 넣은 AI 설정 파일(팀 설정 있음)
        for f in rs.repo.files:
            if R.AI_CFG.search(f['path']) and f['path'] not in cfg_paths and not is_example(f['path']):
                add_inst('tool_trace', rs, f['path'], None, '팀 AI 설정 파일(내 커밋 아님)', 'excluded')
    tool_T = bool(trace_A)
    for rs, p, sha, why in trace_A[:20]:
        add_ev('tool_trace', rs, path=p, sha=sha or None, rule=f'ai.tool_trace.{why}@1')
    if not tool_T:
        seen = set()
        for rs, p, sha, why in weak_tool:
            if tcount['tool_trace'] >= CAP_TOOL or (rs.repo.key, p or sha) in seen:
                continue
            seen.add((rs.repo.key, p or sha))
            files = [(p, 1, 120)] if p else []
            target('tool_trace', rs, 'ai.tool_trace', files, commits=[sha] if sha and not p else [], rule_result=dict(reason=why), priority=tcount['tool_trace'] + 1,
                   group='TOOL', stop_rule='first_yes')
    n_has_tool = tcount['tool_trace']
    data['variables']['ai.tool_trace'] = dict(
        name='AI 도구 흔적', role='tf', value=True if tool_T else (False if not n_has_tool else None),
        state='value_rule' if tool_T else ('zero_unused' if not n_has_tool else None), unit='T/F',
        by_repo={k: True for k in sorted({x[0].repo.key for x in trace_A})}, instances=inst['tool_trace'], evidence=evid['tool_trace'],
        definition='「Claude 정의」(B-41 후보 A): 내 커밋이 넣거나 바꾼 AI 설정 파일(CLAUDE.md·AGENTS.md·GEMINI.md·.cursorrules·.cursor/·.claude/·copilot-instructions.md·'
                   '.windsurfrules·.clinerules·.aider*·.codex/·.junie/·.kiro/·.roo/·.mcp.json 등, 기록 전체), 내 커밋의 AI 공동 작성자 꼬리표, '
                   '내 커밋·PR 본문의 생성 표시 중 하나라도 있으면 T. 생성기가 쓴 설정 파일(Next.js 지문)·빈 파일은 뺀다. F는 "흔적 못 찾음"(안 씀이 아님).',
        notes=f'꼬리표 커밋 수 {sum(1 for _, rs in reps if rs for c in rs.repo.commits if c["own"] and c["ai_coauthor"])} · 생성기 지문 제외 {gen_cfg} · '
              f'후보 B(AI 작성자 + 내가 커미터) 커밋 {len(trace_B)} · S5 대상 {n_has_tool}건',
        s5_waiting=n_has_tool)
    alt_tool = dict(A=tool_T, B=tool_T or bool(trace_B), C=tool_T or bool(pairs_B), A_without_trailers=any(x[3] == 'ai-config-file' for x in trace_A))

    # ======================= no_trace 표본(레포마다 최대 3개: 연동·기법)
    for repo, rs in reps:
        if rs is None:
            continue
        if any(t['repo'] == rs.repo.key for t in targets):
            continue
        if by_repo_int.get(rs.repo.key) or tech_by_repo.get(rs.repo.key):
            continue
        if any(d for d in rs.dep_traces):
            continue
        code = sorted(((f.get('my_lines') or 0), f['path']) for f in rs.repo.files
                      if rs.kinds.get(f['path']) == 'code' and (f.get('size') or 0) < 300_000 and f.get('prog_lang'))
        code = [c for c in code if c[0] >= 20]
        if not code:
            continue
        top = [c[1] for c in code[-2:]][::-1]
        files = [(p, 1, 200) for p in top]
        target('integrations', rs, 'ai.integration', files, rule_result=dict(reason='no-trace-sample', rule_value=0), trace='no_trace', priority=9)
        target('techniques', rs, 'ai.technique.any', files, rule_result=dict(reason='no-trace-sample', rule_value=0), trace='no_trace', priority=9)

    data['s5_targets'] = targets
    data['definition_choices'] = [
        dict(item='B-37 AI 연동 1개의 단위', choice='B (제공자, API 종류) 쌍 + 로컬 모델 포함',
             why='문서 시작값이 15까지라 제공자 수(A)로는 4단계 이상에 거의 닿지 않는다. 쌍(B)은 한 제공자의 대화·임베딩·음성을 다른 연동으로 보아 실제 연동 폭을 센다. '
                 'C(호출 함수마다)는 같은 API를 여러 함수에서 부르면 부풀고 「같은 것은 한 번」(규칙 5)과 어긋난다. 로컬 모델(Hugging Face·Whisper·YOLO 등)도 모델을 코드에 붙인 연동이라 넣고, 뺀 값은 따로 보인다.',
             alternatives=dict(A_providers=alt_int['A_providers'], B_pairs=alt_int['B_pairs'], B_pairs_no_local=alt_int['B_pairs_no_local'],
                               C_endpoint_x_function=alt_int['C_endpoint_x_function'])),
        dict(item='B-38 AI 기법 목록·ML 시작값 읽기', choice='LLM 10 + ML 10 목록, LLM·ML을 따로 세서 각자 시작값으로 단계 → 높은 쪽',
             why='부록 후보 목록(LLM 9·ML 8)에 지시문 예의 프롬프트 체인·ML 모델 학습과 11-19 매핑 예의 데이터 버전 관리를 더했다. '
                 '데이터·ML 사람이 LLM 기법으로 재면 늘 낮게 나오므로 ML 시작값(1/2/3/4/6)을 따로 쓰는 읽기가 문서의 괄호 표기와 맞는다. 단계는 S6이 낸다.',
             alternatives={'전체(LLM+ML 합)': alt_tech['full_llm_plus_ml'], 'LLM만': alt_tech['llm_only'], 'ML만': alt_tech['ml_only'],
                           '좁은 목록(지시문 예 6개)': alt_tech['narrow_list']}),
        dict(item='B-39 AI 기능 1개의 단위', choice='A 사용자 진입점(HTTP API·화면·CLI·봇 명령)',
             why='규칙으로 잴 수 있고(호출 그래프), 사용자가 쓰는 기능이라는 이름 뜻과 맞는다. C(최상위 함수)는 내부 함수까지 세어 연동 수와 경계가 흐려지고, B(LLM 묶음)는 재현이 안 된다. '
                 '표본 8건 중 5건이 CLI 인터페이스 없는 실험·수집 스크립트였다 → 스크립트는 argparse·click·typer·fire·sys.argv가 있을 때만 CLI 기능으로 센다(넣은 값은 A_plus_plain_scripts).',
             alternatives=alt_feat),
        dict(item='B-40 검증된 AI PR', choice='(가) AI 생성 PR + ① 머지(분석 브랜치, 작성자 본인)',
             why='「제안」은 (가)+②지만 색인에 리뷰가 없어 ②를 못 잰다(API 추가 호출 필요). 혼자 하는 레포는 자기 PR을 승인할 수 없어 ②면 늘 0이다. '
                 '(나)는 AI 기능 PR이라 연동·기능과 겹친다. 사람이 머지한 것을 지금은 "검증"으로 본다 — 사용자 확인 필요.',
             alternatives=alt_pr),
        dict(item='B-41 AI 도구 흔적', choice='A 내 커밋의 AI 설정 파일·AI 공동 작성자 꼬리표·생성 표시',
             why='「문서」 규칙 8(설정 파일에 그 기능이 쓰이도록 적힘)에 맞는 근거만 쓴다. B(AI 작성 커밋)는 계정 확인을 통과하지 못한 커밋이라 본인 확인 결정과 부딪치고, '
                 'C(LangChain 등)는 AI 연동 수와 겹친다.',
             alternatives=alt_tool),
    ]
    data['stats'] = dict(
        repos=len(reps), repos_failed=sum(1 for _, rs in reps if rs is None), files_scanned=sum(len(rs.scans) for _, rs in reps if rs),
        parse_errors=sum(len(rs.parse_err) for _, rs in reps if rs), unreadable=sum(len(rs.unreadable) for _, rs in reps if rs),
        reclassified_out_dir=sum(rs.reclassified for _, rs in reps if rs), extra_blame=sum(rs.own.extra_blame for _, rs in reps if rs),
        parsers=dict(collections.Counter(v for _, rs in reps if rs for v in rs.parser.values())),
        s5=dict(collections.Counter(t['var'] + ':' + t['trace'] for t in targets)), seconds=round(time.time() - t0, 1),
        gaps=['tree-sitter 없음: JS/TS·Java/Kotlin·Dart는 줄 규칙(line-rule)', 's2lib GENERATED의 out/ 조각이 소스 경로(adapter/out/ 등)를 생성 파일로 분류 → 여기서 다시 나눔(blame 다시 돔)',
              'PR 리뷰·base 브랜치가 색인에 없음 → 검증 ② 못 잼, base는 머지 커밋이 분석 브랜치에 닿는지로 대신함'])
    return data


# ---------------------------------------------------------------- S5 반영
def finalize(person, data, answers):
    out = json.loads(json.dumps(data))
    V = out['variables']
    by_var = collections.defaultdict(list)
    for t in out.get('s5_targets', []):
        a = answers.get(t['target_id'])
        by_var[t['var']].append((t, a))
    summary = {}
    for var, lst in by_var.items():
        vk = 'ai.' + var
        v = V.get(vk)
        if v is None:
            continue
        waiting = sum(1 for t, a in lst if a is None)
        failed = sum(1 for t, a in lst if a and a.get('decision') == 'unknown')
        yes = [(t, a) for t, a in lst if a and a.get('decision') == 'yes']
        add = 0
        from_llm = []
        if var == 'integrations':
            pairs = set(v.get('parts', {}).get('pairs', []))
            for t, a in yes:
                vals = a.get('value')
                vals = vals if isinstance(vals, list) else ([vals] if vals else [f'LLM/{t["target_id"]}'])
                for x in vals:
                    x = str(x).strip()[:80]
                    if x and x not in pairs:
                        pairs.add(x)
                        add += 1
                        from_llm.append(dict(target=t['target_id'], value=x, evidence=a.get('evidence'), model=a.get('model'), trace=t.get('trace')))
            v['parts']['pairs'] = sorted(pairs)
        elif var == 'techniques':
            parts = v.get('parts', {})
            have = set(parts.get('llm_list', [])) | set(parts.get('ml_list', []))
            for t, a in yes:
                tech = (t.get('rule_result') or {}).get('technique')
                if tech == 'any' or t['template'] == 'ai.technique.any' or not tech:
                    vals = a.get('value')
                    vals = vals if isinstance(vals, list) else ([vals] if vals else [])
                    techs = [x for x in vals if x in R.TECH_LLM + R.TECH_ML]
                else:
                    techs = [tech]
                for tech in techs:
                    if tech not in have:
                        have.add(tech)
                        add += 1
                        from_llm.append(dict(target=t['target_id'], value=tech, evidence=a.get('evidence'), model=a.get('model'), trace=t.get('trace')))
            parts['llm_list'] = sorted(x for x in have if x in R.TECH_LLM)
            parts['ml_list'] = sorted(x for x in have if x in R.TECH_ML)
            parts['llm'], parts['ml'] = len(parts['llm_list']), len(parts['ml_list'])
        elif var == 'features':
            seen = set()
            for t, a in yes:
                lab = re.sub(r'\s+', ' ', str(a.get('value') or t['target_id'])).strip().lower()[:80]
                k = (t['repo'], lab)
                if k not in seen:
                    seen.add(k)
                    add += 1
                    from_llm.append(dict(target=t['target_id'], value=lab, evidence=a.get('evidence'), model=a.get('model'), trace=t.get('trace')))
        elif var == 'verified_prs':
            for t, a in yes:
                add += 1
                from_llm.append(dict(target=t['target_id'], value=(t.get('rule_result') or {}).get('pr'), evidence=a.get('evidence'), model=a.get('model')))
        elif var == 'tool_trace':
            if yes:
                t, a = yes[0]
                from_llm.append(dict(target=t['target_id'], value=True, evidence=a.get('evidence'), model=a.get('model')))
        base = v.get('value')
        if var == 'tool_trace':
            if v.get('value') is True:
                pass
            elif from_llm:
                v['value'], v['state'] = True, 'value_llm'
            elif waiting:
                v['value'], v['state'] = None, None
            elif failed and not any(a and a.get('decision') == 'no' for t, a in lst):
                v['value'], v['state'] = None, 'unknown_failed'
            else:
                v['value'], v['state'] = False, 'value_rule'
        else:
            rule_v = base if isinstance(base, (int, float)) and not isinstance(base, bool) else 0
            newv = rule_v + add
            if add:
                v['value'], v['state'] = newv, 'value_llm'
            elif rule_v:
                v['value'], v['state'] = rule_v, 'value_rule'
            elif waiting:
                v['value'], v['state'] = None, None
            elif failed and not any(a and a.get('decision') == 'no' for t, a in lst if t.get('trace') == 'has_trace'):
                has = [t for t, a in lst if t.get('trace') == 'has_trace']
                v['value'], v['state'] = (None, 'unknown_failed') if has else (0, 'zero_unused')
            else:
                v['value'], v['state'] = 0, ('value_rule' if any(t.get('trace') == 'has_trace' for t, a in lst) else 'zero_unused')
        v['from_llm'] = from_llm
        v['s5'] = dict(sent=sum(1 for t, a in lst if a and a.get('decision') != 'skipped'), yes=len(yes),
                       no=sum(1 for t, a in lst if a and a.get('decision') == 'no'), unknown=failed, waiting=waiting,
                       skipped=sum(1 for t, a in lst if a and a.get('decision') == 'skipped'),
                       no_trace_yes=sum(1 for t, a in yes if t.get('trace') == 'no_trace'))
        v['s5_waiting'] = waiting
        summary[var] = v['s5']
    out['finalized'] = dict(summary=summary, complete=not any(s['waiting'] for s in summary.values()))
    return out


# ---------------------------------------------------------------- S5 질문 틀
_BASE = ('너는 lv-stat의 AI 기술 변수 판정기다. 보낸 자료(줄 번호가 붙은 파일 범위·커밋·PR)만 근거로 판단한다. '
         '줄 앞에 * 가 붙은 줄이 이 사람이 쓴 줄(blame)이다. 근거 줄은 * 가 붙은 줄이어야 한다(노트북처럼 * 표시가 없으면 그 파일 줄).\n'
         '「문서」 lv-calc 공통 규칙 8(썼다고 보는 기준): 내 코드에서 실제로 호출한 곳 1곳 이상, 또는 설정 파일에 그 기능이 쓰이도록 적혀 있음. '
         '주석·끄는 값·예시 파일이면 X. 의존성 파일이나 import 줄에만 있으면 X.\n'
         '「문서」 규칙 5: 그 카테고리 파일을 바꾼 내 커밋·내 줄만 센다. 테스트 코드·생성 파일·복사한 외부 코드는 세지 않는다.\n')
_TECH_DEF = '\n'.join(f'- {t}: {R.TECH_NAME[t]}' for t in R.TECH_LLM + R.TECH_ML)
S5_TEMPLATES = {
    'ai.integration': dict(
        system=_BASE + 'AI 연동 = 내 줄에서 AI 모델·서비스(LLM·임베딩·음성·비전·이미지 생성 API, 또는 코드에 붙인 사전 학습 모델: Hugging Face·Whisper·YOLO·Ollama·TFLite 등)를 '
                       '실제로 부르는 곳. ML 학습 프레임워크(torch·sklearn·keras)로 직접 학습만 하는 코드는 연동이 아니다(그건 기법). 연동 1개 = 서로 다른 (제공자, API 종류) 쌍.',
        question='이 자료의 이 사람 줄(*)에서 AI 모델·서비스를 실제로 부르는 곳이 있는가? yes = 있음(호출 줄을 근거로), no = 없음(import·의존성·주석·설정 이름만 있거나 남의 줄뿐). '
                 'yes면 value에 부른 것을 "제공자/종류" 문자열 배열로 적는다(종류: chat·embedding·speech-to-text·text-to-speech·vision·image-generation·model-inference·rerank·nlp). '
                 '예: ["OpenAI/chat", "OpenAI/embedding"].'),
    'ai.feature': dict(
        system=_BASE + 'AI 기능 = 사용자에게 보이는 진입점(HTTP API 엔드포인트·화면·CLI 명령·봇 명령) 하나가 AI 호출의 결과를 쓰는 것. 노트북 셀·시험 코드·내부 함수만 있는 것은 기능이 아니다.',
        question='규칙 결과에 적힌 AI 호출(이 사람 줄)의 결과를 쓰는 사용자 진입점이 자료 안에 있는가? yes = 있음(진입점 줄 또는 AI 호출 줄을 근거로), no = 진입점이 없음(실험 코드·노트북·안 쓰이는 함수). '
                 '모르면 unknown과 need(부르는 쪽 파일·함수 이름). yes면 value에 진입점을 짧게 적는다(예: "POST /api/chat", "화면 ChatPage", "CLI main.py", "봇 명령 ask").'),
    'ai.pr': dict(
        system=_BASE + 'AI PR = AI 코딩 도구(Claude Code·Copilot·Cursor·Codex·ChatGPT 등)로 만들었다고 PR이나 그 커밋에 적힌 PR. AI 기능을 만든 PR(예: "ChatGPT API 붙임")은 AI PR이 아니다.',
        question='이 PR(제목·설명·커밋)은 AI 코딩 도구로 작성했다고 적힌 PR인가? yes = AI 도구로 코드·글을 만들었다는 표시가 있음(근거: pr:#번호 또는 sha), '
                 'no = AI 기능 이야기이거나 도구 이름만 지나가듯 나옴.'),
    'ai.tool_trace': dict(
        system=_BASE + 'AI 도구 흔적 = 이 사람이 개발에 AI 코딩 도구를 쓴 흔적: 직접 쓴 AI 도구 설정 파일(규칙·지침), 커밋의 AI 공동 작성자 꼬리표, 커밋·PR의 생성 표시. '
                       '생성기(프레임워크 초기화 도구)가 자동으로 만든 설정 파일은 흔적이 아니다.',
        question='이 자료는 이 사람이 개발에 AI 코딩 도구를 썼다는 흔적인가? yes = 이 사람이 직접 쓰거나 고친 AI 도구 설정·지침이거나, 커밋이 AI 도구 사용을 밝힘(근거 줄·sha), '
                 'no = 생성기가 만든 파일 그대로이거나 AI 기능 이야기뿐.'),
    'ai.technique.any': dict(
        system=_BASE + 'AI 기법 목록(이 목록 안의 것만):\n' + _TECH_DEF + '\n기법 1개 = 목록 항목 하나를 이 사람 줄에서 실제로 한 근거가 1곳 이상.',
        question='이 자료의 이 사람 줄(*)에서 위 목록의 AI 기법을 실제로 한 곳이 있는가? yes면 value에 한 기법의 영문 키 배열(예: ["rag", "model_training"])과 근거 줄. '
                 'no = 목록의 기법이 없음.'),
}
_TECH_Q = {
    'rag': '검색한 문서·조각을 LLM 프롬프트에 넣어 답을 만들게 하는가(검색 결과가 실제로 프롬프트로 들어가야 함)?',
    'embedding_search': '임베딩(벡터)을 저장하고 유사도로 검색하는가(벡터 DB 검색 또는 코사인 유사도 비교)?',
    'tool_calling': 'LLM에 도구(함수) 정의를 넘겨 모델이 부를 도구를 고르게 하는가?',
    'agent': '모델이 도구를 고르고 결과를 다시 넣는 여러 단계 루프(에이전트)를 만드는가?',
    'mcp': 'MCP(Model Context Protocol) 서버나 클라이언트를 만드는가?',
    'structured_output': 'LLM 출력을 JSON 스키마·파서로 구조화해 받는가?',
    'prompt_template': '프롬프트를 템플릿(변수 자리를 둔 틀)·별도 파일로 관리하고 코드에서 불러 쓰는가?',
    'prompt_chain': '앞 LLM 호출의 결과를 다음 LLM 호출의 입력으로 넣는 체인을 만드는가?',
    'llm_eval': 'LLM 출력을 정해진 기준·데이터로 평가하는 코드가 있는가?',
    'fine_tuning': 'LLM(또는 사전 학습 언어 모델)을 자기 데이터로 미세 조정하는가?',
    'model_training': 'ML 모델을 자기 데이터로 학습시키는가(fit·학습 루프)?',
    'data_split': '학습·검증·시험 데이터를 나누는가?',
    'preprocess_pipeline': '전처리 단계를 파이프라인으로 묶어 학습·추론에 같이 쓰는가?',
    'hyperparam_search': '하이퍼파라미터를 여러 값으로 탐색하는가(격자·무작위·베이즈 탐색)?',
    'cross_validation': '교차 검증을 하는가?',
    'transfer_learning': '사전 학습 가중치를 불러 자기 데이터로 다시 학습하는가?',
    'eval_metrics': '학습한 모델을 평가 지표로 재는가?',
    'model_save': '학습한 모델을 파일로 저장하는가?',
    'serving': '학습한 모델을 불러 API·화면에서 추론 결과를 주는가?',
    'data_versioning': '데이터·모델 버전을 도구(DVC 등)로 관리하는가?',
}
for _t, _q in _TECH_Q.items():
    S5_TEMPLATES[f'ai.technique.{_t}'] = dict(
        system=_BASE + 'AI 기법 목록:\n' + _TECH_DEF + '\n기법 1개 = 목록 항목 하나를 이 사람 줄에서 실제로 한 근거가 1곳 이상.',
        question=f'기법 "{_t}"({R.TECH_NAME[_t]}): {_q} yes = 이 사람 줄(*)에서 그렇게 함(근거 줄), no = 아님(신호만 있고 실제로는 다른 일). '
                 '모르면 unknown과 need(더 볼 파일·줄).')


def main():
    for pid in [a for a in sys.argv[1:] if re.match(r'^P\d\d$', a)]:
        t0 = time.time()
        person = L.load_person(pid)
        data = extract(person)
        L.write_vars(pid, KEY, data)
        V = data['variables']
        print(pid, 'int', V['ai.integrations']['value'], 'tech', V['ai.techniques']['value'], V['ai.techniques']['parts']['llm'], V['ai.techniques']['parts']['ml'],
              'feat', V['ai.features']['value'], 'pr', V['ai.verified_prs']['value'], 'tool', V['ai.tool_trace']['value'],
              's5', data['stats']['s5'], round(time.time() - t0, 1), 's', flush=True)


if __name__ == '__main__':
    main()
