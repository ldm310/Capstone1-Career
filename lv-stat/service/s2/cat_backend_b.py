#!/usr/bin/env python3
"""lv-stat 2단계 스파이크(버림용, 제품 코드 아님, 2026-11-26): 백엔드 API·로그·부가 기술 영역 추출기.

맡은 범위(부록 A): A-2.2.3 API·외부 API·캐시(API1~API9, API-C1) · A-2.2.4 로그(LOG1~LOG6, LOG-C1) · A-2.3 상한 ·
A-2.4 규칙 · A-2.5 원인 찾은 기록(LOG6) · A-2.7 부가 기술 영역 EXT1~4(가점 재료) · A-2.9 [AI 확인](A안·B안 둘 다 계산).

usage: python3 -I cat_backend_b.py P01 [P02 ...]   → s2/out/<pid>/vars-backend_b.json
- extract(person): 규칙만. LLM·네트워크를 쓰지 않는다. 받은 코드는 git으로 읽기만 한다(실행·빌드·설치 없음).
- finalize(person, data, answers): S5 답을 반영한다. 답이 없는 대상은 '대기'로 남긴다.
- 게이트·라우트·백엔드 파일은 backend_gate(gate·context)를 그대로 쓴다(같은 판정을 다시 하지 않음).
- 파서: Python 표준 ast(backend_gate의 oc 색인) + tokenize(가리기), Java·Kotlin·JS·TS는 주석·문자열을 가린 정규식(스파이크,
  tree-sitter 없음). 결과 notes에 남긴다.
- 결과에는 위치(경로·줄·SHA)만 남기고 코드 내용·이름·이메일은 넣지 않는다.
"""
import bisect
import collections
import io
import json
import os
import re
import sys
import time
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.setrecursionlimit(10000)
import s2lib as L  # noqa: E402
import backend_gate as G  # noqa: E402

oc = G.oc
CAT = 'backend_b'
RULE_V = '@1'
PARSER_NOTE = 'Python: 표준 ast(oc 색인)+tokenize · Java/Kotlin/JS/TS: 주석·문자열을 가린 정규식(스파이크, tree-sitter 아님)'

# ---------------- 「문서」 숫자(백엔드 v5 §3·§4 표)
API_POINTS = dict(API1=1, API2=1, API3=1, API4=1, API5=1, API6=1, API7=1, API8=1, API9=2)
LOG_POINTS = dict(LOG1=1, LOG2=1, LOG3=1, LOG4=1, LOG5=2, LOG6=2)
CAP_MAX = {'API-C1': 2, 'LOG-C1': 2}

# ---------------- LOG6 후보(옛 스파이크 owncheck_spike.FIX_STRICT 그대로) + 원인 낱말(우선순위용)
FIX_STRICT = re.compile(r'(?i)(^|[^a-z])(fix(e[sd])?|bug(fix)?|hot-?fix|resolve[sd]?)([^a-z]|$)|버그|오류|에러|고침|고쳤|픽스|핫픽스|문제\s*해결|해결')
FIX_LOOSE = re.compile(r'수정')
CAUSE = re.compile(r'(?i)원인|때문|이유|because|caused by|cause[sd]?\b|due to|root cause')
DOC_EXT = re.compile(r'\.(md|mdx|rst|adoc|txt)$', re.I)

HEALTH = re.compile(r'(?i)(^|/)(health|healthz|healthcheck|health-check|ping|actuator|readiness|liveness|ready|live)(/|$)')
DOCS_PATH = re.compile(r'(?i)(^|/)(swagger[\w-]*|api-docs|v3/api-docs|redoc|openapi(\.json)?)(/|$)')

CONF_RX = re.compile(r'(^|/)(application[^/]*\.(ya?ml|properties)|bootstrap[^/]*\.(ya?ml|properties)|logback[^/]*\.xml|log4j2?[^/]*\.(xml|properties|ya?ml|json)|'
                     r'docker-compose[^/]*\.ya?ml|compose[^/]*\.ya?ml|settings[^/]*\.py|logging[^/]*\.(conf|ini|ya?ml|json)|gunicorn[^/]*\.(py|conf)|'
                     r'ecosystem\.config\.[cm]?js|pm2[^/]*\.json|nest-cli\.json|config/[^/]*\.(ya?ml|json|py|[cm]?[jt]s)|[^/]*\.properties)$', re.I)
EXAMPLE = re.compile(r'(?i)(^|[/._-])(example|sample|template|dist|bak|tmpl)([/._-]|$)')
ENV_FILE = re.compile(r'(^|/)\.env')


# ======================================================================== 공통 부품
def mask_py(src):
    """-> (주석 지운 코드, 주석·문자열을 가린 코드). 길이·줄 바꿈을 그대로 둔다."""
    nc, mk = list(src), list(src)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception:
        return src, src
    starts = [0]
    for line in src.splitlines(True):
        starts.append(starts[-1] + len(line))

    def off(rc):
        r, c = rc
        return min(len(src), (starts[r - 1] if r - 1 < len(starts) else len(src)) + c)
    fsm = getattr(tokenize, 'FSTRING_MIDDLE', -1)
    for t in toks:
        if t.type == tokenize.COMMENT:
            for i in range(off(t.start), off(t.end)):
                nc[i] = ' '
                mk[i] = ' '
        elif t.type == tokenize.STRING:
            a, b = off(t.start), off(t.end)
            q = re.match(r'^[rRbBuUfF]*("""|\'\'\'|"|\')', t.string)
            ql = len(q.group(0)) if q else 1
            qe = len(q.group(1)) if q else 1
            for i in range(a + ql, max(a + ql, b - qe)):
                if mk[i] != '\n':
                    mk[i] = ' '
        elif t.type == fsm:
            for i in range(off(t.start), off(t.end)):
                if mk[i] != '\n':
                    mk[i] = ' '
    return ''.join(nc), ''.join(mk)


def mask_conf(p, t):
    """설정 파일: 주석 줄(#·!·;)과 XML 주석을 가린다(주석·끄는 값은 근거가 아님). 길이를 그대로 둔다."""
    if p.endswith('.xml'):
        t2 = re.sub(r'<!--[\s\S]*?-->', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), t)
    else:
        t2 = re.sub(r'(?m)^[ \t]*[#!;].*$', lambda m: ' ' * len(m.group(0)), t)
        t2 = re.sub(r'(?m)(\s)#(?![{!]).*$', lambda m: m.group(1) + ' ' * (len(m.group(0)) - 1), t2) if re.search(r'\.(ya?ml|toml|properties|ini|cfg|conf)$', p) else t2
    return t2, t2


class LineIdx:
    def __init__(self, s):
        self.st = [0] + [m.end() for m in re.finditer('\n', s)]

    def line(self, pos):
        return bisect.bisect_right(self.st, pos)


def norm_path(p):
    p = (p or '').strip().strip('\'"`')
    p = re.sub(r'\$\{[^}]*\}', '{}', p)
    p = re.sub(r'\(\?P<\w+>[^)]*\)|\{[^}]*\}|:\w+\??|<[^>]+>|\[[^\]]+\]', '{}', p)
    p = p.replace('^', '').replace('$', '')
    p = '/' + p.strip('/')
    return re.sub(r'/+', '/', p)


def split_words(seg):
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', seg)
    return [w.lower() for w in re.split(r'[^A-Za-z0-9]+', s) if w]


def ev(rc, path=None, line=None, sha=None, rule=None, note=None, end=None):
    return L.evidence(rc.repo, path=path, line=line, sha=sha, rule=rule, note=note, end=end)


class RC:
    """게이트를 통과한 백엔드 레포 하나의 문맥."""

    def __init__(self, repo, grec):
        self.repo, self.key, self.g = repo, repo.key, grec
        self.ctx = G.context(repo)
        self.o = self.ctx['oc']
        self.fws = [fw for fw, x in (grec.get('frameworks') or {}).items() if x.get('pass')]
        self.bfiles = sorted({p for fw in self.fws for p in self.ctx['backend_files'].get(fw, [])})
        self.bset = set(self.bfiles)
        self.roots = [r['dir'] for r in self.ctx['roots'] if set(r['fw']) & set(self.fws)] or ['']
        self._t, self._mk, self._li = {}, {}, {}

    def text(self, p):
        t = self.ctx['texts'].get(p)
        if t is not None:
            return t
        if p not in self._t:
            f = self.repo.file(p)
            self._t[p] = G.batch_read(self.repo, [p]).get(p) if f else None
        return self._t[p]

    def masks(self, p):
        if p not in self._mk:
            t = self.text(p)
            if t is None:
                self._mk[p] = None
            elif p.endswith('.py'):
                self._mk[p] = mask_py(t)
            elif re.search(r'\.(java|kt|kts|js|jsx|ts|tsx|mjs|cjs|groovy|scala)$', p):
                self._mk[p] = oc.strip_c(t)
            else:
                self._mk[p] = mask_conf(p, t)
        return self._mk[p]

    def li(self, p):
        if p not in self._li:
            m = self.masks(p)
            self._li[p] = LineIdx(m[0]) if m else None
        return self._li[p]

    def own(self, p):
        return G.own_set(self.repo, p)

    def mine(self, p, ln):
        s = self.own(p)
        return bool(s) and ln in s

    def mine_ratio(self, p):
        """파일의 내 줄 비율(빈 줄·주석 뺌). 공용 설정 과반(규칙 9)에 쓴다."""
        m, tot = G.my_code_lines(self.repo, p, self.text(p))
        if m is None or not tot:
            f = self.repo.file(p)
            if f and f.get('my_lines') is not None and f.get('lines'):
                return f['my_lines'] / f['lines']
            return None
        return m / tot

    def files_kind(self, kinds, roots=True):
        out = []
        for f in self.repo.files:
            k = G.kind_of(f)
            if k in kinds and (not roots or any(G.under(f['path'], d) for d in self.roots)):
                out.append(f['path'])
        return out

    def configs(self):
        out = []
        for f in self.repo.files:
            p = f['path']
            if ENV_FILE.search(p) or G.kind_of(f) in ('vendor', 'generated', 'test') or EXAMPLE.search(p.rsplit('/', 1)[-1]):
                continue
            if CONF_RX.search(p) and (f.get('size') or 0) < 400_000:
                out.append(p)
        return out

    def scan(self, paths, rx, which=1, mine_only=True, limit=400):
        """paths에서 rx에 맞는 곳 -> [(path, line, matchtext)]. which=0 주석만 지운 코드, 1 문자열까지 가린 코드."""
        out = []
        for p in paths:
            m = self.masks(p)
            if not m:
                continue
            s = m[which]
            for mo in rx.finditer(s):
                ln = self.li(p).line(mo.start())
                if mine_only and not self.mine(p, ln):
                    continue
                out.append((p, ln, mo.group(0)[:80]))
                if len(out) >= limit:
                    return out
        return out


# ======================================================================== 라우트 → API 목록
DRF_GEN = {'ListAPIView': ['GET:list'], 'CreateAPIView': ['POST'], 'ListCreateAPIView': ['GET:list', 'POST'], 'RetrieveAPIView': ['GET'],
           'UpdateAPIView': ['PUT', 'PATCH'], 'DestroyAPIView': ['DELETE'], 'RetrieveUpdateAPIView': ['GET', 'PUT', 'PATCH'],
           'RetrieveDestroyAPIView': ['GET', 'DELETE'], 'RetrieveUpdateDestroyAPIView': ['GET', 'PUT', 'PATCH', 'DELETE'],
           'ListView': ['GET:list'], 'DetailView': ['GET'], 'CreateView': ['GET', 'POST'], 'UpdateView': ['GET', 'POST'], 'DeleteView': ['GET', 'POST'],
           'FormView': ['GET', 'POST'], 'TemplateView': ['GET'], 'RedirectView': ['GET']}
VIEWSET_ALL = {'ModelViewSet': ['GET:list', 'POST', 'GET:detail', 'PUT:detail', 'PATCH:detail', 'DELETE:detail'], 'ReadOnlyModelViewSet': ['GET:list', 'GET:detail']}
MIXIN = {'ListModelMixin': ['GET:list'], 'CreateModelMixin': ['POST'], 'RetrieveModelMixin': ['GET:detail'], 'UpdateModelMixin': ['PUT:detail', 'PATCH:detail'],
         'DestroyModelMixin': ['DELETE:detail']}
VIEWSET_M = {'list': 'GET:list', 'create': 'POST', 'retrieve': 'GET:detail', 'update': 'PUT:detail', 'partial_update': 'PATCH:detail', 'destroy': 'DELETE:detail'}


def pseudo_cls(cls):
    return dict(lang='py', file=cls['file'], cls=cls['name'], name='<class>', params=[], code=cls.get('code', ''), masked=cls.get('code', ''),
                line=cls['line'], annos='')


def django_expand(o, e):
    """urls.py 한 줄 → [(verb, 붙일 경로, 핸들러, 목록 여부, 자동 생성 여부, rest 여부)]"""
    out = []
    ref, hs, router = e['name'], e['handlers'], e['kind'] == 'drf-router'
    if ref[:1].isupper():
        cls = next((c for c in o.classes.get(ref, []) if c.get('lang') == 'py'), None)
        if not cls:
            return out
        hdr, meths = cls.get('header', ''), cls['methods']
        bases = set(re.findall(r'\b(\w+)\b', hdr))
        rest = bool(re.search(r'APIView|ViewSet|generics\.|Serializer|rest_framework', hdr + cls.get('code', '')[:3000]))
        got = set()

        def add(spec, h, auto):
            v, _, kind = spec.partition(':')
            sub = '/{}' if (kind == 'detail' and router) else ''
            k = (v, sub)
            if k in got:
                return
            got.add(k)
            out.append((v, sub, h, kind == 'list', auto, rest))
        for mn in ('get', 'post', 'put', 'patch', 'delete'):
            if mn in meths:
                add(mn.upper() + (':list' if mn == 'get' and any(b in bases for b in ('ListAPIView', 'ListView', 'ListCreateAPIView')) else ''), meths[mn][0], False)
        for mn, spec in VIEWSET_M.items():
            if mn in meths:
                add(spec, meths[mn][0], False)
        for b in bases:
            for spec in VIEWSET_ALL.get(b, []):
                mn = next((k for k, v in VIEWSET_M.items() if v == spec), None)
                add(spec, meths[mn][0] if mn in meths else pseudo_cls(cls), mn not in meths)
            for spec in MIXIN.get(b, []):
                mn = next((k for k, v in VIEWSET_M.items() if v == spec), None)
                add(spec, meths[mn][0] if mn in meths else pseudo_cls(cls), mn not in meths)
            for spec in DRF_GEN.get(b, []):
                add(spec, pseudo_cls(cls), False)
        for mn, fl in meths.items():
            for f in fl:
                am = re.search(r'@action\s*\(([^)]*)\)', f.get('annos') or '')
                if am:
                    ms = re.findall(r'(get|post|put|patch|delete)', am.group(1).lower()) or ['get']
                    det = re.search(r'detail\s*=\s*True', am.group(1))
                    for v in sorted(set(ms)):
                        k = (v.upper(), ('/{}/' if det else '/') + mn)
                        if k not in got:
                            got.add(k)
                            out.append((v.upper(), k[1], f, not det and v == 'get', False, True))
        if not out:
            out.append(('GET', '', pseudo_cls(cls), False, False, rest))
        return out
    for f in hs:
        if f.get('cls') is not None:
            continue
        an = f.get('annos') or ''
        av = re.search(r'@api_view\s*\(\s*\[([^\]]*)\]', an) or re.search(r'@require_http_methods\s*\(\s*\[([^\]]*)\]', an)
        if av:
            verbs = re.findall(r'GET|POST|PUT|PATCH|DELETE', av.group(1).upper()) or ['GET']
        elif re.search(r'@api_view\b', an):
            verbs = ['GET']
        elif '@require_POST' in an:
            verbs = ['POST']
        elif re.search(r'@require_(GET|safe)\b', an):
            verbs = ['GET']
        else:
            verbs = sorted(set(re.findall(r'request\.method\s*==\s*[\'"](GET|POST|PUT|PATCH|DELETE)[\'"]', f['code'])) | {'GET'})
        rest = bool(re.search(r'@api_view|JsonResponse|\bResponse\s*\(', an + f['code']))
        for v in verbs:
            out.append((v, '', f, False, False, rest))
        break
    return out


def h_range(h):
    """핸들러 줄 범위(정의 줄 ~ 끝 줄)."""
    n = (h.get('code') or '').count('\n')
    if h.get('lang') in ('java', 'ts'):
        n -= (h.get('annos') or '').count('\n')
    return h['line'], h['line'] + max(0, n)


def build_apis(rc):
    apis, seen = [], set()
    o = rc.o
    for e in rc.ctx['routes']:
        fw = e.get('fw')
        if fw not in rc.fws:
            continue
        if e['kind'] in ('drf-generic', 'drf-view', 'drf-action', 'py-fview'):
            continue                                   # Django는 urls.py 줄에서 한 번만 센다
        if e['kind'] in ('django-url', 'drf-router'):
            items = [(v, e['path'] + sub, h, lst, auto, rest) for v, sub, h, lst, auto, rest in django_expand(o, e)]
        else:
            h = e['handlers'][0] if e['handlers'] else None
            items = [(v, e['path'], h, None, False, None) for v in e['verb'].split('/')]
        for v, p, h, lst, auto, rest in items:
            np_ = norm_path(p)
            hk = (h['file'], h['line']) if h else (e['file'], e['line'])
            k = (fw, v, np_, hk)
            if k in seen:
                continue
            seen.add(k)
            a, b = h_range(h) if h else (e['line'], e['line'])
            api = dict(id=f'{rc.key}#{len(apis) + 1}', repo=rc.key, fw=fw, verb=v, path=np_, file=e['file'], line=e['line'], h=h,
                       hfile=h['file'] if h else e['file'], hstart=a, hend=b, kind=e['kind'], list_hint=lst, auto=auto, rest_hint=rest)
            api['health'] = bool(HEALTH.search(np_)) or bool(DOCS_PATH.search(np_))
            apis.append(api)
    for api in apis:
        A, B, C = api_mine(rc, api)
        api.update(mine=A, mine_def=B, mine_any=C)
    return apis


def api_mine(rc, api):
    """「제안」 [B-43] A: 라우트 정의 + 핸들러 본문의 줄 중 내 줄 과반 · B: 라우트 정의 줄이 내 줄 · C: 핸들러에 내 줄 1줄 이상"""
    m, tot = G.my_code_lines(rc.repo, api['hfile'], rc.text(api['hfile']), api['hstart'], api['hend'])
    if m is None:
        return None, None, None
    m2 = t2 = 0
    if api['file'] != api['hfile'] or not (api['hstart'] <= api['line'] <= api['hend']):
        x, y = G.my_code_lines(rc.repo, api['file'], rc.text(api['file']), api['line'], api['line'])
        m2, t2 = x or 0, y or 0
    A = (tot + t2) > 0 and (m + m2) * 2 > (tot + t2)
    B = rc.mine(api['file'], api['line'])
    C = (m + m2) > 0
    return A, B, C


# ---------------- 핸들러 모양
WRAP = {'ResponseEntity', 'List', 'ArrayList', 'Page', 'Slice', 'Optional', 'Set', 'Collection', 'Iterable', 'Mono', 'Flux', 'Map', 'HashMap', 'Object',
        'String', 'Long', 'Integer', 'Boolean', 'Void', 'Double', 'Float', 'Promise', 'Array', 'Record', 'Partial', 'Pick', 'Omit', 'Observable',
        'CompletableFuture', 'Callable', 'DeferredResult', 'HttpEntity', 'JsonNode', 'Any', 'Dict', 'Union', 'Sequence', 'Iterator', 'Number', 'Readonly',
        'StreamingResponseBody', 'Resource', 'ModelAndView', 'HttpResponse', 'JsonResponse', 'Response', 'JSONResponse', 'RedirectView', 'UUID', 'LocalDateTime'}
DTO_NAME = re.compile(r'(Dto|DTO|Response|Res|Resp|Result|View|Info|Detail|Summary|Vo|VO|Output|Out|Payload|Schema|Read|Public)$')
SIMPLE_T = re.compile(r'^(?:final\s+)?(?:int|long|short|byte|double|float|boolean|char|Integer|Long|Short|Double|Float|Boolean|String|UUID|LocalDate\w*|BigDecimal|'
                      r'number|string|boolean|bigint|str|bool|float|int|Enum\w*|[A-Z]\w*(?:Type|Status|Kind|Category|Role|Enum))$')


class RepoModel:
    """레포의 엔티티·DTO·Pydantic·serializer 이름(응답 모양·비밀번호 상한)."""

    def __init__(self, rc):
        o = rc.o
        self.entities, self.dtos, self.pyd, self.orm, self.ser = {}, set(), {}, {}, {}
        self.mongoose = set()
        for name, cl in o.classes.items():
            for c in cl:
                if c.get('lang') == 'java':
                    if re.search(r'@(?:Entity|Document|Table)\b', c.get('annos') or ''):
                        self.entities[name] = c
                    else:
                        self.dtos.add(name)
                elif c.get('lang') == 'ts':
                    if re.search(r'@(?:Entity|Schema|Table|ObjectType)\s*\(', c.get('annos') or ''):
                        self.entities[name] = c
                    else:
                        self.dtos.add(name)
                elif c.get('lang') == 'py':
                    hdr = c.get('header', '')
                    if re.search(r'models\.Model|\bModel\b|\bBase\b|db\.Model|AbstractUser|AbstractBaseUser|Document|SQLModel', hdr) and not re.search(r'BaseModel|Serializer|Schema', hdr):
                        if 'SQLModel' not in hdr or 'table=True' in hdr:
                            self.orm[name] = c
                    elif re.search(r'BaseModel|SQLModel|Schema\b', hdr):
                        self.pyd[name] = c
                    if re.search(r'Serializer\b', hdr):
                        self.ser[name] = c
        # 상속 사슬(class UserCreate(UserBase) 처럼 Pydantic·ORM 클래스를 이어받은 것)
        for _ in range(4):
            for name, cl in o.classes.items():
                for c in cl:
                    if c.get('lang') != 'py' or name in self.pyd or name in self.orm:
                        continue
                    bases = set(re.findall(r'\b([A-Z]\w*)', c.get('header', '')))
                    if bases & set(self.pyd):
                        self.pyd[name] = c
                    elif bases & set(self.orm):
                        self.orm[name] = c
        for p, (lang, code, masked) in o.files.items():
            if lang == 'ts':
                for mo in re.finditer(r'\b(?:mongoose\s*\.\s*)?model\s*(?:<[^>]*>)?\s*\(\s*[\'"](\w+)[\'"]', code):
                    self.mongoose.add(mo.group(1))
                for mo in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:mongoose\s*\.\s*)?model\s*\(', code):
                    self.mongoose.add(mo.group(1))
            if p.endswith('.prisma'):
                for mo in re.finditer(r'^\s*model\s+(\w+)\s*\{', code, re.M):
                    self.entities.setdefault(mo.group(1), dict(file=p, code='', annos='prisma'))


def java_ret(h):
    """oc 색인의 annos는 '어노테이션 + 접근자 + 반환 타입'(메서드 이름 앞 전부)이다."""
    pre = h.get('annos') or ''
    if re.search(r'\bfun\b', pre):          # Kotlin: 반환 타입은 매개변수 뒤
        sig = (h.get('code') or '')[len(pre):]
        k = sig.find('(')
        if k >= 0:
            q = oc.match(sig, k, '(', ')')
            mo = re.match(r'\s*:\s*([\w.<>?, \[\]]+?)\s*[{=]', sig[q + 1:q + 200])
            return re.sub(r'\s+', '', mo.group(1)) if mo else ''
        return ''
    pre = re.sub(r'@[\w.]+(?:\s*\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))?', ' ', pre)
    pre = re.sub(r'\b(?:public|private|protected|static|final|synchronized|abstract|default|native)\b', ' ', pre)
    pre = re.sub(r'^\s*<[^<>]*(?:<[^<>]*>[^<>]*)*>', ' ', pre.strip())
    return re.sub(r'\s+', '', pre)


def ts_ret(h):
    m = h.get('masked') or ''
    sig = m[len(h.get('annos') or ''):]
    k = sig.find('(')
    if k < 0:
        return ''
    q = oc.match(sig, k, '(', ')')
    mo = re.match(r'\s*:\s*([^{=]+?)\s*(?:=>\s*)?\{', sig[q + 1:q + 300])
    return re.sub(r'\s+', '', mo.group(1)) if mo else ''


def is_rest(rc, api):
    h = api['h']
    if not h:
        return True
    if api['rest_hint'] is not None:
        return api['rest_hint']
    if api['fw'] == 'spring':
        cls = next((c for c in rc.o.classes.get(h.get('cls') or '', []) if c['file'] == h['file']), None)
        ca = cls.get('annos', '') if cls else ''
        if '@RestController' in ca or '@ResponseBody' in ca or '@ResponseBody' in (h.get('annos') or ''):
            return True
        r = java_ret(h)
        return r.startswith(('ResponseEntity', 'HttpEntity')) and 'ModelAndView' not in r
    if api['fw'] == 'nest':
        return '@Render' not in (h.get('annos') or '')
    if api['fw'] == 'express':
        return not re.search(r'\bres\s*\.\s*render\s*\(', h.get('masked') or '')
    if api['fw'] == 'fastapi':
        return not re.search(r'TemplateResponse|HTMLResponse', (h.get('code') or '') + (h.get('annos') or ''))
    return True


def callees(rc, h, depth=1, limit=8):
    """핸들러가 부르는 함수(한두 단계). 서비스 쪽 페이지네이션·검사·외부 호출 확인에 쓴다."""
    out, work, seen = [], [(h, 0)], set()
    while work and len(out) < limit:
        f, d = work.pop(0)
        k = (f['file'], f.get('cls'), f['name'], f['line'])
        if k in seen:
            continue
        seen.add(k)
        if f is not h:
            out.append(f)
        if d >= depth:
            continue
        try:
            for recv, name, this, args, cline in oc.calls_of(f):
                for g in rc.o.resolve_call(f, recv, name, this):
                    work.append((g, d + 1))
        except Exception:
            pass
    return out


# ======================================================================== API 항목
CRUD_VERB = {'create', 'update', 'delete', 'del', 'remove', 'get', 'fetch', 'add', 'insert', 'modify', 'edit', 'save', 'write', 'put', 'set', 'change',
             'retrieve', 'find', 'select', 'regist', 'make', 'post', 'patch', 'read', 'load', 'upsert', 'erase', 'destroy', 'show'}
STRICT_EXTRA = {'list', 'detail', 'view', 'form', 'new', 'search', 'all', 'info'}
AUTH_ACT = {'login', 'logout', 'signin', 'signout', 'signup', 'register', 'join', 'reissue', 'refresh', 'token', 'oauth', 'oauth2', 'callback', 'auth',
            'verify', 'verification', 'withdraw', 'withdrawal', 'password', 'kakao', 'google', 'naver', 'github', 'me', 'check', 'duplicate', 'email', 'code'}


def api2_judge(api):
    """-> (main: 'pass'|'fail'|'auth', strict: 'pass'|'fail', words)"""
    segs = [s for s in api['path'].split('/') if s and s != '{}' and not re.match(r'^(api|v\d+)$', s, re.I)]
    words = [w for s in segs for w in split_words(s)]
    auth = any(w in AUTH_ACT for w in words)
    bad = [w for s in segs for w in (split_words(s)[:1] + split_words(s)[-1:]) if w in CRUD_VERB]
    bad_strict = bad + [w for s in segs for w in split_words(s) if w in STRICT_EXTRA]
    main = 'auth' if auth else ('fail' if bad else 'pass')
    return main, ('fail' if bad_strict else 'pass'), sorted(set(bad_strict))


JAVA_CONSTRAINT = re.compile(r'@(?:NotBlank|NotNull|NotEmpty|Size|Length|Min|Max|Email|Pattern|Positive|PositiveOrZero|Negative|DecimalMin|DecimalMax|Range|Past|Future|'
                             r'PastOrPresent|FutureOrPresent|Digits|URL|Valid[A-Z]\w*|Phone\w*|Password\w*)\b')
TS_CONSTRAINT = re.compile(r'@(?:IsString|IsNotEmpty|IsEmail|Length|MinLength|MaxLength|Min|Max|IsInt|IsNumber|IsPositive|Matches|IsEnum|IsUrl|IsDate\w*|IsBoolean|'
                           r'IsOptional|IsIn|IsUUID|IsPhoneNumber|IsAlphanumeric|ArrayMaxSize|ArrayMinSize|IsArray|ValidateNested|IsDefined|IsMongoId|IsNumberString)\s*\(')
PY_CONSTRAINT = re.compile(r'\b(?:max_length|min_length|max_value|min_value|ge|le|gt|lt|regex|pattern|max_digits|validators|choices)\s*=|'
                           r'\b(?:EmailStr|EmailField|URLField|HttpUrl|constr|conint|confloat|conlist|SlugField|RegexField|IPAddressField|UUIDField)\b|@(?:field_)?validator\s*\(|def\s+validate_\w*\s*\(')
SKIP_PARAM_T = re.compile(r'^(?:HttpServletRequest|HttpServletResponse|ServerHttpRequest|Model|ModelMap|Principal|Authentication|BindingResult|Errors|HttpSession|'
                          r'RedirectAttributes|Locale|SessionStatus|UriComponentsBuilder|Pageable|Sort|WebRequest|HttpHeaders|ServerWebExchange|SessionUser|\w*UserDetails\w*|'
                          r'\w*Principal\w*|Request|Response|NextFunction|FastifyRequest|FastifyReply)$')


EXP_VALID = re.compile(r'(?<![\w.$])(?:validate\w*|celebrate|validationMiddleware|validateRequest|validateBody)\s*\(|(?<![\w.$])(?:body|query|param|check|checkSchema)\s*\(\s*[\'"\[{]|'
                       r'validationResult\s*\(|\bJoi\s*\.|\bz\s*\.\s*object\s*\(|\.(?:parse|safeParse|validate|validateAsync)\s*\(\s*req\s*\.|limits\s*:\s*\{[^}]*fileSize|'
                       r'\.isLength\s*\(|\.isEmail\s*\(|\byup\s*\.')


def dto_class(rc, name, lang):
    name = re.sub(r'<.*', '', name or '').strip().split('.')[-1].strip('[]?')
    for c in rc.o.classes.get(name, []):
        if c.get('lang') == lang or (lang == 'java' and c.get('lang') == 'java'):
            return c
    return None


def class_text(rc, c):
    if not c:
        return ''
    if c.get('lang') == 'py':
        return c.get('code', '')
    m = rc.masks(c['file'])
    if not m:
        return ''
    nc = m[0]
    return nc[max(0, c['start'] - 400):c['end'] + 1] if 'start' in c else ''


def has_validation_dep(rc):
    for p, t in (rc.ctx.get('build_texts') or {}).items():
        t = t or ''
        if re.search(r'validation|hibernate-validator', t):
            return True
        mo = re.search(r"org\.springframework\.boot['\"]?\s*\)?\s*version\s*['\"](\d+)\.(\d+)|<artifactId>spring-boot-starter-parent</artifactId>\s*<version>(\d+)\.(\d+)", t)
        if mo:
            a, b = int(mo.group(1) or mo.group(3)), int(mo.group(2) or mo.group(4))
            if (a, b) < (2, 3):
                return True
    return False


def global_pipe(rc):
    for p in rc.bfiles:
        m = rc.masks(p)
        if m and re.search(r'useGlobalPipes\s*\(\s*new\s+ValidationPipe|provide\s*:\s*APP_PIPE[\s\S]{0,80}ValidationPipe', m[0]):
            return True
    return False


def multipart_limit(rc):
    for p in rc.configs():
        t = rc.text(p) or ''
        if re.search(r'max-file-size|max_file_size|maxFileSize|max-request-size|FILE_UPLOAD_MAX_MEMORY_SIZE|DATA_UPLOAD_MAX_MEMORY_SIZE', t):
            return p
    return None


def api3_judge(rc, api, M):
    """입력 검사. -> (상태, 입력 종류) 상태: pass·fail·noinput·pathonly·unclear"""
    h = api['h']
    if not h:
        return 'unclear', []
    fw, kinds, ok = api['fw'], [], []
    body = (h.get('masked') or '') + ''.join(g.get('masked') or '' for g in callees(rc, h, 1, 6))
    if fw == 'spring':
        cls = next((c for c in rc.o.classes.get(h.get('cls') or '', []) if c['file'] == h['file']), None)
        cval = bool(cls and '@Validated' in (cls.get('annos') or ''))
        dep = has_validation_dep(rc)
        for an, t, n in h.get('params') or []:
            tb = re.sub(r'<.*', '', t or '').strip()
            if not t or SKIP_PARAM_T.match(tb) or re.search(r'@(?:AuthenticationPrincipal|LoginUser|CurrentUser|AuthUser|Login\w*|CurrentMember|AuthMember|RequestHeader|CookieValue|RequestAttribute|SessionAttribute)\b', an or ''):
                continue
            if '@PathVariable' in (an or ''):
                kinds.append('path')
                ok.append(bool(JAVA_CONSTRAINT.search(an) and cval and dep))
                continue
            if 'MultipartFile' in t:
                kinds.append('file')
                ok.append(bool(multipart_limit(rc)) or bool(re.search(r'\.getSize\s*\(\s*\)\s*[<>]', body)))
                continue
            if '@RequestParam' in (an or '') or (SIMPLE_T.match(tb) and '@RequestBody' not in (an or '')):
                kinds.append('query')
                ok.append(bool(JAVA_CONSTRAINT.search(an or '') and cval and dep))
                continue
            kinds.append('body')
            dc = dto_class(rc, t, 'java')
            ct = class_text(rc, dc)
            ok.append(bool(re.search(r'@(?:Valid|Validated)\b', an or '') and JAVA_CONSTRAINT.search(ct) and dep))
    elif fw == 'nest':
        gp = global_pipe(rc)
        an_all = (h.get('annos') or '')
        cls = next((c for c in rc.o.classes.get(h.get('cls') or '', []) if c['file'] == h['file']), None)
        local = bool(re.search(r'@UsePipes\s*\([^)]*ValidationPipe', an_all + (cls.get('annos', '') if cls else '')))
        for deco, t, n, mod in h.get('params') or []:
            if re.search(r'@(?:Body)\s*\(', deco or ''):
                kinds.append('body')
                dc = dto_class(rc, t, 'ts')
                ct = class_text(rc, dc)
                ok.append(bool(TS_CONSTRAINT.search(ct)) and (gp or local or 'ValidationPipe' in (deco or '')))
            elif re.search(r'@(?:Query)\s*\(', deco or ''):
                kinds.append('query')
                dc = dto_class(rc, t, 'ts')
                ok.append(bool(dc and TS_CONSTRAINT.search(class_text(rc, dc))) and (gp or local) or bool(re.search(r'Parse\w*Pipe', deco or '')))
            elif re.search(r'@(?:Param)\s*\(', deco or ''):
                kinds.append('path')
                ok.append(bool(re.search(r'Parse\w*Pipe', deco or '')))
            elif re.search(r'@Uploaded(?:File|Files)\s*\(', deco or ''):
                kinds.append('file')
                ok.append(bool(re.search(r'fileSize|MaxFileSizeValidator|ParseFilePipe', an_all + (deco or ''))))
    elif fw == 'express':
        m = h.get('masked') or ''
        if re.search(r'\breq\s*\.\s*body\b', body):
            kinds.append('body')
        if re.search(r'\breq\s*\.\s*query\b', body):
            kinds.append('query')
        if re.search(r'\breq\s*\.\s*files?\b', body):
            kinds.append('file')
        if re.search(r'\breq\s*\.\s*params\b', body) and not kinds:
            kinds.append('path')
        route_line = ''
        mk = rc.masks(api['file'])
        if mk:
            lines = mk[0].split('\n')
            route_line = '\n'.join(lines[max(0, api['line'] - 1):api['line'] + 2])
        code_chain = (h.get('code') or '') + ''.join(g.get('code') or '' for g in callees(rc, h, 1, 6))
        v = bool(EXP_VALID.search(route_line + '\n' + code_chain))
        ok = [v for _ in kinds]
    elif fw in ('django',):
        code = h.get('code') or ''
        verb = api['verb']
        if verb in ('POST', 'PUT', 'PATCH') or re.search(r'request\.(data|POST|FILES|body)\b', code):
            kinds.append('body')
            cls = next((c for c in rc.o.classes.get(h.get('cls') or '', []) if c.get('lang') == 'py'), None) if h.get('cls') else None
            ctext = (cls.get('code', '') if cls else '') + code
            uses = bool(re.search(r'serializer_class\s*=|Serializer\s*\(|Form\s*\(|form_class\s*=|get_serializer\s*\(', ctext)) or \
                bool(cls and re.search(r'CreateAPIView|UpdateAPIView|ModelViewSet|CreateModelMixin|UpdateModelMixin|CreateView|UpdateView|FormView|ListCreateAPIView|RetrieveUpdate', cls.get('header', '')))
            ok.append(uses and (bool(re.search(r'is_valid\s*\(', ctext)) or bool(cls and re.search(r'APIView|ModelViewSet|Mixin|CreateView|UpdateView|FormView', cls.get('header', '')))))
        elif re.search(r'request\.(GET|query_params)\b', code):
            kinds.append('query')
            ok.append(bool(re.search(r'Serializer\s*\(|Form\s*\(|FilterSet|filterset_class', code)))
    elif fw == 'fastapi':
        for dflt, ann, n in h.get('params') or []:
            if n in ('self', 'request', 'response', 'db', 'session', 'background_tasks') or re.search(r'Depends\s*\(|Session|Request|Response|BackgroundTasks', (dflt or '') + (ann or '')):
                continue
            if re.search(r'UploadFile|File\s*\(', (ann or '') + (dflt or '')):
                kinds.append('file')
                ok.append(bool(re.search(r'\.size\b|len\s*\(\s*await\s+\w+\.read|content_length|max_size', h.get('code') or '')))
                continue
            an = re.sub(r'^(?:Optional|List|list)\[(.*)\]$', r'\1', (ann or '').strip())
            if an in M.pyd:
                kinds.append('body')
                ok.append(bool(PY_CONSTRAINT.search(M.pyd[an].get('code', ''))))
                continue
            if re.search(r'Path\s*\(', dflt or '') or ('{' + n + '}') in (h.get('annos') or ''):
                kinds.append('path')
                ok.append(bool(PY_CONSTRAINT.search(dflt or '')))
                continue
            kinds.append('query')
            ok.append(bool(PY_CONSTRAINT.search(dflt or '')))
    if not kinds:
        return 'noinput', []
    if set(kinds) <= {'path'}:
        return ('pass' if all(ok) else 'pathonly'), kinds
    pay = [o_ for k, o_ in zip(kinds, ok) if k != 'path']
    if all(pay):
        return 'pass', kinds
    # 흔적: 손으로 쓴 검사(길이·형식 비교, 예외 던짐) → 애매한 것
    if re.search(r'\.length\s*(?:\(\s*\))?\s*[<>]=?|len\s*\([^)]*\)\s*[<>]|\.isBlank\s*\(|\.isEmpty\s*\(|\.matches\s*\(|re\.match|test\s*\(|\.size\s*\(\s*\)\s*[<>]|'
                 r'throw\s+new\s+\w*(?:Invalid|Validation|IllegalArgument|BadRequest)\w*|raise\s+\w*(?:Validation|HTTPException)|status\s*\(\s*400\s*\)', body):
        return 'unclear', kinds
    if fw == 'express' and M.mongoose and re.search(r'\.(create|save|insertMany)\s*\(', body):
        return 'unclear', kinds
    return 'fail', kinds


def returned_vars_js(m):
    out = []
    for mo in re.finditer(r'\bres\s*\.\s*(?:status\s*\([^)]*\)\s*\.\s*)?(?:json|send)\s*\(', m):
        q = oc.match(m, mo.end() - 1, '(', ')')
        out.append(m[mo.end():q].strip())
    for mo in re.finditer(r'\breturn\s+([^;\n]+)', m):
        out.append(mo.group(1).strip())
    return out


def db_vars_js(m):
    v = set()
    for mo in re.finditer(r'(?:const|let|var)?\s*(?:\{\s*([\w\s,:]+)\}|(\w+))\s*=\s*(?:await\s+)?([^;\n]+)', m):
        rhs = mo.group(3)
        if G.TS_DB.search(rhs) and not re.search(r'\.select\s*\(|select\s*:|attributes\s*:|projection|\.lean\s*\(\s*\)\s*\.\s*map', rhs):
            if mo.group(2):
                v.add(mo.group(2))
            for x in (mo.group(1) or '').split(','):
                x = x.split(':')[-1].strip()
                if x:
                    v.add(x)
    return v


def api4_judge(rc, api, M):
    """필요한 값만 응답. -> pass·fail·nodata·view·unclear"""
    h = api['h']
    if not h:
        return 'unclear'
    if not is_rest(rc, api):
        return 'view'
    fw = api['fw']
    ents = set(M.entities)
    if fw == 'spring':
        r = java_ret(h)
        ids = [x for x in re.findall(r'\b[A-Z]\w*', r) if x not in WRAP]
        if any(x in ents for x in ids):
            return 'fail'
        if any(x in M.dtos or DTO_NAME.search(x) for x in ids):
            return 'pass'
        if r in ('void', 'Void', 'String', 'ResponseEntity<Void>', 'ResponseEntity<String>', 'boolean', 'Boolean', 'long', 'Long', 'int', 'Integer', 'ResponseEntity<Boolean>', 'ResponseEntity<Long>'):
            return 'nodata'
        m = h.get('masked') or ''
        rets = ' '.join(re.findall(r'\breturn\s+([^;]+);', m))
        if re.search(r'new\s+\w*(?:Dto|DTO|Response|Res|Result)\b|\.(?:toDto|toResponse|from|of|fromEntity)\s*\(|\.map\s*\(|put\s*\(', rets + m):
            return 'pass'
        if re.search(r'[Rr]epository\s*\.\s*(?:find|get)', rets):
            return 'fail'
        return 'unclear'
    if fw == 'nest':
        r = ts_ret(h)
        ids = [x for x in re.findall(r'\b[A-Z]\w*', r) if x not in WRAP]
        if any(x in ents for x in ids):
            return 'fail'
        if any(DTO_NAME.search(x) or (x in M.dtos and x not in ents) for x in ids):
            return 'pass'
        if r in ('void', 'Promise<void>', 'string', 'Promise<string>', 'boolean', 'Promise<boolean>'):
            return 'nodata'
        chain = (h.get('masked') or '') + ''.join(g.get('masked') or '' for g in callees(rc, h, 1, 4))
        if re.search(r'plainToInstance|plainToClass|new\s+\w*(?:Dto|Response)\b|\.map\s*\(|select\s*:', chain):
            return 'pass'
        if re.search(r'\breturn\s+(?:await\s+)?this\s*\.\s*\w*(?:[Rr]epo\w*|prisma\s*\.\s*\w+|[Mm]odel)\s*\.\s*(?:find|save|create|update)\w*\s*\(', chain):
            return 'fail'
        return 'unclear'
    if fw == 'express':
        m = h.get('masked') or ''
        rv = returned_vars_js(m)
        if not rv:
            return 'nodata' if not re.search(r'res\s*\.\s*(?:json|send)', m) else 'unclear'
        dbv = db_vars_js(m)
        bad = False
        good = False
        for x in rv:
            ids = set(re.findall(r'(?<![\w.$])([A-Za-z_$][\w$]*)', x))
            if G.TS_DB.search(x) and not re.search(r'select|attributes|projection', x):
                bad = True
            elif ids & dbv:
                if re.search(r'\.\s*map\s*\(', x):
                    good = True
                else:
                    bad = True
            elif x.startswith('{') or re.search(r'^[\'"`]', x):
                good = True
        if bad:
            return 'fail'
        return 'pass' if good else 'unclear'
    if fw == 'django':
        cls = next((c for c in rc.o.classes.get(h.get('cls') or '', []) if c.get('lang') == 'py'), None) if h.get('cls') else None
        text = (cls.get('code', '') if cls else '') + (h.get('code') or '')
        sers = set(re.findall(r'serializer_class\s*=\s*(\w+)', text)) | set(re.findall(r'\b(\w+Serializer)\s*\(', text))
        if not sers:
            if re.search(r'model_to_dict|serializers\.serialize\s*\(|\.values\s*\(\s*\)', text):
                return 'fail'
            if re.search(r'JsonResponse\s*\(\s*\{|Response\s*\(\s*\{', text):
                return 'pass'
            if re.search(r'JsonResponse|Response\s*\(', text):
                return 'unclear'
            return 'nodata'
        res = []
        for s in sers:
            sc = M.ser.get(s)
            if not sc:
                res.append('unclear')
                continue
            f = sc.get('assigns', {}).get('Meta.fields', '')
            if '__all__' in f:
                res.append('fail')
            elif f or sc.get('assigns', {}).get('Meta.exclude') or not re.search(r'ModelSerializer', sc.get('header', '')):
                res.append('pass')
            else:
                res.append('unclear')
        return 'fail' if 'fail' in res else ('pass' if all(x == 'pass' for x in res) else 'unclear')
    if fw == 'fastapi':
        an = h.get('annos') or ''
        rm = re.search(r'response_model\s*=\s*([\w\[\]., ]+)', an)
        names = re.findall(r'\b([A-Z]\w*)', rm.group(1)) if rm else []
        mo = re.search(r'\)\s*->\s*([^:]+):', (h.get('code') or '').split('\n', 3)[0] + ''.join((h.get('code') or '').split('\n')[1:3]))
        if not names and mo:
            names = re.findall(r'\b([A-Z]\w*)', mo.group(1))
        names = [n for n in names if n not in WRAP]
        if any(n in M.orm for n in names):
            return 'fail'
        if any(n in M.pyd for n in names):
            return 'pass'
        code = h.get('code') or ''
        if re.search(r'\breturn\s*\{', code):
            return 'pass'
        if re.search(r'\breturn\s+(?:db_)?\w+\s*$', code, re.M) and re.search(r'\.query\s*\(|\.get\s*\(|\.scalars?\s*\(|select\s*\(', code):
            return 'fail'
        return 'unclear' if re.search(r'\breturn\b', code) else 'nodata'
    return 'unclear'


PAGE_PARAM = re.compile(r'(?i)\b(?:page|size|limit|offset|cursor|skip|take|per_page|perPage|pageSize|page_size|pageNum|lastId|last_id)\b')


def api6_judge(rc, api, M, settings_page):
    """목록 API인지, 페이지네이션이 있는지. -> (is_list, 'pass'|'fail'|'unclear')"""
    h = api['h']
    if api['verb'] not in ('GET', 'ANY') or not h:
        return False, None
    fw = api['fw']
    m = h.get('masked') or ''
    chain = m + ''.join(g.get('masked') or '' for g in callees(rc, h, 1, 5))
    is_list = api['list_hint']
    if fw == 'spring':
        r = java_ret(h)
        if is_list is None:
            is_list = bool(re.search(r'\b(?:List|Page|Slice|Set|Collection|Iterable|Flux)<|\[\]', r)) or \
                (not is_rest(rc, api) and bool(re.search(r'addAttribute\s*\([^)]*(?:findAll|List|list|getAll)\w*', m)))
        pg = bool(re.search(r'\bPageable\b|@PageableDefault|PageRequest\s*\.\s*of|\bPage<|\bSlice<|\.setFirstResult|\.limit\s*\(|LIMIT', chain)) or \
            any(PAGE_PARAM.search(n or '') for an, t, n in (h.get('params') or []))
    elif fw == 'nest':
        r = ts_ret(h)
        if is_list is None:
            is_list = bool(re.search(r'\[\]|Array<|Paginat\w*|Page<', r)) or bool(re.match(r'(?i)^(findAll|getAll|list|getList|find\w+s|get\w+s|search\w*)$', h['name'])) \
                and '{}' not in api['path']
        pg = bool(re.search(r'\btake\s*:|\bskip\s*:|\.skip\s*\(|\.limit\s*\(|\.take\s*\(|offset|Paginat|PageOptions|cursor', chain)) or \
            any(PAGE_PARAM.search((n or '') + ' ' + (t or '')) for d, t, n, mo in (h.get('params') or []))
    elif fw == 'express':
        if is_list is None:
            is_list = '{}' not in api['path'] and bool(re.search(r'\.find\s*\(\s*(?:\{[^}]*\})?\s*\)|\.findAll\s*\(|\.findMany\s*\(|\.findAndCountAll\s*\(|\.select\s*\(\s*\)|SELECT', chain + (h.get('code') or '')))
        pg = bool(re.search(r'req\s*\.\s*query\s*\.\s*(?:page|limit|offset|cursor|size|skip|take|per_?page)|\.skip\s*\(|\.limit\s*\(|\btake\s*:|\bskip\s*:|\boffset\s*:|\blimit\s*:', chain)) or \
            bool(re.search(r'(?i)LIMIT\s+[?$\d]|OFFSET', h.get('code') or ''))
    elif fw == 'django':
        cls = next((c for c in rc.o.classes.get(h.get('cls') or '', []) if c.get('lang') == 'py'), None) if h.get('cls') else None
        text = (cls.get('code', '') if cls else '') + (h.get('code') or '')
        if is_list is None:
            is_list = bool(re.search(r'many\s*=\s*True|\.objects\s*\.\s*(?:all|filter)\s*\(', h.get('code') or '')) and '{}' not in api['path']
        pg = bool(re.search(r'pagination_class\s*=\s*(?!None)|paginate_by\s*=|Paginator\s*\(|paginate_queryset', text)) or \
            (settings_page and not re.search(r'pagination_class\s*=\s*None', text) and bool(cls))
    elif fw == 'fastapi':
        an = h.get('annos') or ''
        if is_list is None:
            is_list = bool(re.search(r'response_model\s*=\s*(?:typing\.)?(?:List|list|Sequence)\[|->\s*(?:List|list|Sequence)\[', an + (h.get('code') or '')[:400])) or \
                (bool(re.search(r'\.all\s*\(\s*\)', h.get('code') or '')) and '{}' not in api['path'])
        pg = any(PAGE_PARAM.search(n or '') for d, a, n in (h.get('params') or [])) or bool(re.search(r'\bPage\[|\.offset\s*\(|\.limit\s*\(|paginate\s*\(', an + (h.get('code') or '')))
    else:
        return False, None
    if not is_list:
        return False, None
    return True, ('pass' if pg else 'fail')


# ---------------- API5 오류 응답 통일
STATUS_JAVA = re.compile(r'HttpStatus\s*\.\s*([A-Z_]+)|\.status\s*\(\s*(\d{3})\s*\)|HttpStatusCode\s*\.\s*valueOf\s*\(\s*(\d{3})')
STATUS_ANY = re.compile(r'\b(?:status(?:_code)?|statusCode)\s*[=:(]\s*(\d{3})|status\s*\.\s*HTTP_(\d{3})|HTTPStatus\s*\.\s*(\w+)|HTTP_(\d{3})_\w+|\b([45]\d\d)\b')


def api5_repo(rc):
    """-> dict(state, ok, evidence, note). 전역 처리 + 같은 모양 + 상태 코드 2종 이상(한 레포 안, 「제안」[B-57])."""
    best = dict(ok=False, why='전역 예외 처리 없음', ev=None, trace=None)
    o = rc.o
    for name, cl in o.classes.items():
        for c in cl:
            if c['file'] not in rc.bset and not c['file'].endswith('.prisma'):
                continue
            if c.get('lang') == 'java' and re.search(r'@(?:Rest)?ControllerAdvice\b', c.get('annos') or ''):
                txt = class_text(rc, c)
                handlers = re.findall(r'@ExceptionHandler', txt)
                st = set(x[0] or x[1] or x[2] for x in STATUS_JAVA.findall(txt))
                # 오류 코드 enum에서 상태를 고르는 경우
                if re.search(r'getStatus\s*\(|getHttpStatus\s*\(|\.status\s*\(\s*\w+\.get\w*Status', txt):
                    for en, ecl in o.classes.items():
                        for e2 in ecl:
                            if e2.get('kind') == 'enum' and re.search(r'(?i)error|code|exception', en):
                                st |= set(x[0] or x[1] or x[2] for x in STATUS_JAVA.findall(class_text(rc, e2)))
                ln = c.get('line') or rc.li(c['file']).line(c['start'])
                mine = (rc.mine_ratio(c['file']) or 0) > 0.5 or rc.mine(c['file'], ln)
                rets = set(re.findall(r'ResponseEntity<\s*(\w+)', txt))
                same = len(rets) <= 1 or bool(rets & {'ErrorResponse', 'ApiResponse', 'ErrorDto', 'CommonResponse', 'ExceptionResponse'}) or len(rets - {'Object', 'String'}) <= 1
                rec = dict(ok=bool(handlers) and len(st) >= 2 and same and mine, why=f'처리기 {len(handlers)}·상태 {len(st)}종·같은 모양 {same}·내 줄 {mine}',
                           ev=ev(rc, path=c['file'], line=ln, rule='backend.api.API5.spring.advice' + RULE_V), trace=(c['file'], ln))
                if rec['ok'] or not best['trace']:
                    best = rec
                if rec['ok']:
                    return best
            if c.get('lang') == 'ts' and re.search(r'@Catch\s*\(', c.get('annos') or '') and re.search(r'ExceptionFilter', c.get('header') or ''):
                txt = class_text(rc, c)
                reg = any(re.search(r'useGlobalFilters\s*\(|APP_FILTER', (rc.masks(p) or ('', ''))[0]) for p in rc.bfiles)
                st = set(re.findall(r'HttpStatus\s*\.\s*([A-Z_]+)', txt)) | set(re.findall(r'\b([45]\d\d)\b', txt))
                if re.search(r'getStatus\s*\(\s*\)', txt):
                    st.add('dynamic')
                ln = c.get('line') or rc.li(c['file']).line(c['start'])
                mine = rc.mine(c['file'], ln) or (rc.mine_ratio(c['file']) or 0) > 0.5
                rec = dict(ok=reg and len(st) >= 2 and mine and bool(re.search(r'\.json\s*\(|\.send\s*\(', txt)),
                           why=f'등록 {reg}·상태 {len(st)}종·내 줄 {mine}', ev=ev(rc, path=c['file'], line=ln, rule='backend.api.API5.nest.filter' + RULE_V), trace=(c['file'], ln))
                if rec['ok'] or not best['trace']:
                    best = rec
                if rec['ok']:
                    return best
    for p in rc.bfiles:
        m = rc.masks(p)
        if not m:
            continue
        nc, mk = m
        if p.endswith(('.js', '.ts', '.mjs', '.cjs')):
            for mo in re.finditer(r'\(\s*(err|error|e)\s*(?::\s*\w+)?\s*,\s*(req|request)\s*(?::\s*\w+)?\s*,\s*(res|response)\s*(?::\s*\w+)?\s*,\s*(next)\s*(?::\s*\w+)?\s*\)\s*(?:=>)?\s*\{', mk):
                b = mo.end() - 1
                e = oc.match(mk, b, '{', '}')
                body = nc[b:e]
                st = set(re.findall(r'\b([45]\d\d)\b', body))
                if re.search(r'(?:err|error|e)\s*\.\s*(?:status|statusCode)', body):
                    st.add('dynamic')
                ln = rc.li(p).line(mo.start())
                rec = dict(ok=len(st) >= 2 and bool(re.search(r'\.json\s*\(|\.send\s*\(', body)) and rc.mine(p, ln), why=f'에러 미들웨어 상태 {len(st)}종',
                           ev=ev(rc, path=p, line=ln, rule='backend.api.API5.express.error-mw' + RULE_V), trace=(p, ln))
                if rec['ok'] or not best['trace']:
                    best = rec
                if rec['ok']:
                    return best
        if p.endswith('.py'):
            for mo in re.finditer(r'@\w+\s*\.\s*exception_handler\s*\(|\.add_exception_handler\s*\(|@\w+\s*\.\s*errorhandler\s*\(', mk):
                ln = rc.li(p).line(mo.start())
                st = set(re.findall(r'status_code\s*=\s*(\d{3})|status\.HTTP_(\d{3})', nc))
                st = {a or b for a, b in st}
                if re.search(r'exc\s*\.\s*status_code', nc):
                    st.add('dynamic')
                rec = dict(ok=len(st) >= 2 and rc.mine(p, ln), why=f'예외 처리기 상태 {len(st)}종', ev=ev(rc, path=p, line=ln, rule='backend.api.API5.py.exception-handler' + RULE_V), trace=(p, ln))
                if rec['ok'] or not best['trace']:
                    best = rec
                if rec['ok']:
                    return best
    for p in rc.configs():
        if p.endswith('.py'):
            t = rc.text(p) or ''
            mo = re.search(r'[\'"]EXCEPTION_HANDLER[\'"]\s*:', t)
            if mo:
                ln = t.count('\n', 0, mo.start()) + 1
                rec = dict(ok=rc.mine(p, ln), why='DRF EXCEPTION_HANDLER 등록', ev=ev(rc, path=p, line=ln, rule='backend.api.API5.django.exception-handler' + RULE_V), trace=(p, ln))
                if rec['ok']:
                    return rec
                best = rec if not best['trace'] else best
    return best


# ---------------- API7 외부 API
EXT_CALL = [
    ('java', re.compile(r'\b(?:\w*[Rr]estTemplate)\s*\.\s*(?:exchange|getForObject|getForEntity|postForObject|postForEntity|put|delete|patchForObject|execute)\s*\(|'
                        r'\b\w*[Ww]ebClient\b[\s\S]{0,200}?\.\s*(?:retrieve|exchangeToMono|exchange)\s*\(|\b\w*[Rr]estClient\s*\.\s*(?:get|post|put|delete|patch)\s*\(\s*\)|'
                        r'\.newCall\s*\(|\bHttpClient\s*\.\s*new\w*\s*\(|\.openConnection\s*\(|\b\w*[Mm]ailSender\s*\.\s*send\s*\(|\bJsoup\s*\.\s*connect\s*\(|'
                        r'\b(?:amazonS3|amazonS3Client|s3Client|s3|s3Template)\s*\.\s*(?:putObject|getObject|deleteObject|upload|download|generatePresignedUrl|getUrl)\s*\(|'
                        r'\b\w*(?:openAi|OpenAi|openai|chatClient|ChatClient|gemini|Gemini)\w*\s*\.\s*(?:create\w*|call|prompt|chat\w*|generate\w*)\s*\(')),
    ('ts', re.compile(r'\baxios\s*(?:\.\s*(?:get|post|put|delete|patch|request|head))?\s*\(|\b(?:fetch|got|superagent|needle)\s*\(\s*(?![\'"`]/)|'
                      r'\b\w*(?:[Aa]pi|[Cc]lient|[Hh]ttp|[Ii]nstance)\s*\.\s*(?:get|post|put|delete|patch)\s*\(\s*(?![\'"`]\s*/)|\.sendMail\s*\(|\b(?:s3|s3Client|S3)\s*\.\s*(?:send|upload|putObject|getObject|getSignedUrl\w*)\s*\(|'
                      r'\bopenai\s*\.\s*\w+(?:\s*\.\s*\w+)*\s*\.\s*create\s*\(|\b\w*(?:openai|anthropic|genAI|gemini)\w*\s*\.\s*(?:chat|messages|completions|models)\b[\s\S]{0,60}?\(')),
    ('py', re.compile(r'\brequests\s*\.\s*(?:get|post|put|delete|patch|request|head)\s*\(|\bhttpx\s*\.\s*(?:get|post|put|delete|patch|request)\s*\(|'
                      r'\b(?:session|client|http)\s*\.\s*(?:get|post|put|delete|patch)\s*\(\s*(?:f?[\'"]https?:|url|\w+_url|API|BASE)|urllib\.request\.urlopen\s*\(|\burlopen\s*\(|'
                      r'\bsmtplib\s*\.\s*SMTP(?:_SSL)?\s*\(|\bsend_mail\s*\(|\.chat\s*\.\s*completions\s*\.\s*create\s*\(|\.messages\s*\.\s*create\s*\(|openai\s*\.\s*\w+\s*\.\s*create\s*\(|'
                      r'\.generate_content\s*\(|\.(?:upload_file|upload_fileobj|put_object|get_object|generate_presigned_url)\s*\(')),
]
TIMEOUT_CFG = re.compile(r'(?i)setConnectTimeout|setReadTimeout|connectTimeout\s*\(|readTimeout\s*\(|setConnectionRequestTimeout|responseTimeout\s*\(|CONNECT_TIMEOUT_MILLIS|'
                         r'ReadTimeoutHandler|\.timeout\s*\(\s*Duration|connect-timeout|read-timeout|connectTimeout\s*[:=]|readTimeout\s*[:=]|mail\.smtp\.(?:connection)?timeout|'
                         r'setConnectionTimeout|setSocketTimeout|apiCallTimeout|apiCallAttemptTimeout|\btimeout\s*[:=]\s*\d|AbortSignal\s*\.\s*timeout|signal\s*:\s*\w*[Ss]ignal|'
                         r'\btimeout\s*=\s*[\w(.]|connect_timeout|read_timeout|ClientTimeout\s*\(|Timeout\s*\(\s*\d')
FAIL_HANDLE = re.compile(r'\.catch\s*\(|\.onStatus\s*\(|\.onErrorResume\s*\(|\.onErrorReturn\s*\(|\.onErrorMap\s*\(|\.retry\w*\s*\(|@Retryable|@Retry\b|@CircuitBreaker|'
                         r'axiosRetry|axios-retry|@retry\b|tenacity|Retry\s*\(|max_retries|retries\s*[:=]|raise_for_status\s*\(')
LOCAL_URL = re.compile(r'localhost|127\.0\.0\.1|0\.0\.0\.0|host\.docker\.internal|[\'"`]/api/')
KIND5 = [('결제', re.compile(r'(?i)iamport|portone|toss|stripe|kakaopay|payment|billing|paypal|nicepay|inicis')),
         ('메일', re.compile(r'(?i)mail|smtp|sendgrid|\bses\b|mailgun|nodemailer')),
         ('지도', re.compile(r'(?i)map|geocod|directions|tmap|kakao\.com/v2/local|naver.*geocode|place')),
         ('AI', re.compile(r'(?i)openai|anthropic|claude|gemini|genai|huggingface|gpt|llm|chatClient|completions|cohere|groq|ollama')),
         ('파일 저장소', re.compile(r'(?i)\bs3\b|s3client|amazons3|bucket|cloudinary|minio|firebase.*storage|gcs|blob'))]


def in_try(mk, pos, lang):
    """pos가 try 블록 안에 있는지(간단히)."""
    if lang == 'py':
        ls = mk[:pos].split('\n')
        cur = ls[-1]
        ind = len(cur) - len(cur.lstrip())
        for line in reversed(ls[:-1][-80:]):
            s = line.strip()
            if not s:
                continue
            li_ = len(line) - len(line.lstrip())
            if li_ < ind:
                if s.startswith('try:'):
                    return True
                if s.startswith(('def ', 'async def ', 'class ')):
                    return False
                ind = li_
        return False
    for mo in re.finditer(r'\btry\s*\{', mk[max(0, pos - 6000):pos]):
        b = max(0, pos - 6000) + mo.end() - 1
        if oc.match(mk, b, '{', '}') > pos:
            return True
    return False


def api7_sites(rc, five_only=False):
    """외부 호출 지점(내 줄) -> [dict(path, line, kind, timeout, fail, state)]"""
    out = []
    repo_timeout = []
    for p in rc.bfiles + rc.configs():
        m = rc.masks(p)
        if m and TIMEOUT_CFG.search(m[0]):
            repo_timeout.append(p)
    for p in rc.bfiles:
        m = rc.masks(p)
        if not m:
            continue
        nc, mk = m
        lang = 'py' if p.endswith('.py') else 'java' if p.endswith(('.java', '.kt')) else 'ts'
        rx = next(r for l_, r in EXT_CALL if l_ == lang)
        for mo in rx.finditer(mk):
            ln = rc.li(p).line(mo.start())
            if not rc.mine(p, ln):
                continue
            q = mo.end() - 1
            args = nc[q:oc.match(mk, q, '(', ')') + 1] if q < len(nc) and nc[q] == '(' else nc[mo.start():mo.start() + 200]
            ctxs = nc[max(0, mo.start() - 300):mo.start() + 400]
            if LOCAL_URL.search(args[:300]) or re.match(r'\(\s*[\'"`]/', args):
                continue
            if re.search(r'(?i)redis|cache|prisma|mongo|knex|pool|sequelize|typeorm|socket|elastic|kafka|queue|bull|supabase\.from', mo.group(0)):
                continue
            if lang == 'ts' and re.search(r'(^|/)(pages|app)/(?!api)', p):
                continue
            kind = next((k for k, r in KIND5 if r.search(ctxs + ' ' + p)), '그 밖')
            if five_only and kind == '그 밖':
                continue
            to = bool(TIMEOUT_CFG.search(args)) or bool(TIMEOUT_CFG.search(nc)) or \
                (lang == 'java' and bool(re.search(r'[Rr]estTemplate|[Ww]ebClient|[Rr]estClient|Feign|mailSender', mo.group(0))) and bool(repo_timeout))
            fl = in_try(mk, mo.start(), lang) or bool(FAIL_HANDLE.search(nc[mo.start():mo.start() + 600])) or bool(re.search(r'@Retryable|@Retry\b|@CircuitBreaker|@retry\b', nc[max(0, mo.start() - 3000):mo.start()]))
            st = 'pass' if (to and fl) else ('unclear' if (fl and not to and repo_timeout) else 'fail')
            out.append(dict(path=p, line=ln, kind=kind, timeout=to, fail=fl, state=st))
    for p in rc.bfiles:      # OpenFeign 인터페이스(호출 지점 = 선언, 타임아웃은 설정)
        m = rc.masks(p)
        if m and '@FeignClient' in m[1]:
            mo = re.search(r'@FeignClient', m[1])
            ln = rc.li(p).line(mo.start())
            if rc.mine(p, ln):
                to = any(re.search(r'(?i)connect-?timeout|read-?timeout', rc.text(c) or '') for c in rc.configs())
                out.append(dict(path=p, line=ln, kind='그 밖', timeout=to, fail=bool(re.search(r'fallback|ErrorDecoder', m[0])), state='unclear' if to else 'fail'))
    return out


# ---------------- API8 캐시(가점형)
def api8_repo(rc):
    """-> dict(state: 'pass'|'wrong'|'unused'|'unclear', why, ev, trace)"""
    allf = rc.bfiles + rc.configs()
    cacheable = rc.scan(rc.bfiles, re.compile(r'@Cacheable\b|@CachePut\b'), 1, True, 20)
    redis_set = rc.scan(rc.bfiles, re.compile(r'opsForValue\s*\(\s*\)\s*\.\s*set\s*\(|\.setex\s*\(|\.setEx\s*\(|\bcache\s*\.\s*set\s*\(|\.set\s*\([^;\n]*(?:[\'"]EX[\'"]|\bEX\s*:|ex\s*=|timeout\s*=)|'
                                                  r'@cache_page\s*\(|cache_page\s*\(|new\s+NodeCache\s*\(|cacheManager\s*\.\s*set\s*\(|@cache\s*\(\s*expire|CacheModule\s*\.\s*register'), 1, True, 20)
    if not cacheable and not redis_set:
        trace = rc.scan(allf, re.compile(r'@EnableCaching|spring-boot-starter-cache|spring\.cache|redis|Redis|lru_cache|CACHES\s*='), 1, False, 3)
        return dict(state='unused', why='캐시 쓰는 곳 없음', ev=None, trace=trace[0] if trace else None)
    if cacheable:
        enabled = bool(rc.scan(allf, re.compile(r'@EnableCaching'), 1, False, 1))
        ttl = bool(rc.scan(allf, re.compile(r'entryTtl\s*\(|expireAfterWrite|expireAfterAccess|time-to-live|timeToLive|spec\s*[:=][^\n]*expireAfter|\.ttl\s*\(|Duration\s*\.\s*of\w+[\s\S]{0,40}Ttl'), 0, False, 1))
        evict = bool(rc.scan(rc.bfiles, re.compile(r'@CacheEvict\b|@CachePut\b|\.evict\s*\(|\.clear\s*\(\s*\)'), 1, True, 1))
        p, ln, _ = cacheable[0]
        e = ev(rc, path=p, line=ln, rule='backend.api.API8.spring.cacheable' + RULE_V)
        if enabled and ttl and evict:
            return dict(state='pass', why='@Cacheable + @EnableCaching + TTL + 삭제', ev=e, trace=(p, ln))
        if not enabled:
            return dict(state='wrong', why='@EnableCaching 없음(작동 연결 없음)', ev=e, trace=(p, ln))
        return dict(state='unclear', why=f'TTL {ttl}·삭제 {evict}', ev=e, trace=(p, ln))
    p, ln, _ = redis_set[0]
    e = ev(rc, path=p, line=ln, rule='backend.api.API8.manual-ttl' + RULE_V)
    nc = (rc.masks(p) or ('', ''))[0]
    seg = '\n'.join(nc.split('\n')[max(0, ln - 3):ln + 2])
    if re.search(r'(?i)refresh|token|blacklist|auth|session|verif|otp|code|mail|lock', seg):
        return dict(state='unused', why='Redis를 토큰·인증 저장에 씀(캐시 아님)', ev=e, trace=(p, ln))
    return dict(state='unclear', why='손으로 쓴 TTL 저장(캐시인지·삭제 경로 확인 필요)', ev=e, trace=(p, ln))


# ---------------- API9 테스트
TEST_CALL = re.compile(r'(?:perform|request\s*\([^)]*\)|client|self\.client|api_client|testClient|TestClient\s*\([^)]*\)|webTestClient|restTemplate|mockMvc|supertest\s*\([^)]*\)|agent)\s*'
                       r'[\s\S]{0,40}?\.\s*(?:get|post|put|patch|delete)\s*\(|\b(?:get|post|put|patch|delete)\s*\(\s*["\'`]/', re.I)
ASSERT = re.compile(r'\bassert\w*|\bexpect\s*\(|andExpect|\.expect\s*\(|assertThat|assertEquals|should\b|verify\s*\(|self\.assert\w+|\.to(?:Be|Equal|Have)\w*\s*\(')
ONLY_AUTH = re.compile(r'isUnauthorized|isForbidden|\b40[13]\b|HTTP_40[13]|UNAUTHORIZED|FORBIDDEN')


def test_index(rc):
    """내 테스트 파일 -> (경로 문자열 목록, 부르는 클래스·메서드 이름, url 이름)."""
    tfiles = [p for p in rc.files_kind(('test',)) if re.search(r'\.(java|kt|py|ts|js)$', p)]
    texts = G.batch_read(rc.repo, tfiles)
    paths, names, urlnames = [], collections.Counter(), set()
    for p in tfiles:
        t = texts.get(p)
        if not t:
            continue
        own = rc.own(p)
        if not own:
            continue
        lines = t.split('\n')
        for i, line in enumerate(lines, 1):
            if i not in own:
                continue
            wl = [lines[i - 1]]
            for nx in lines[i:i + 25]:            # 이 테스트 함수 안에서만(다음 테스트 시작에서 끊음)
                if re.search(r'@Test\b|@ParameterizedTest|^\s*(?:it|test)\s*\(|def\s+test_|@DisplayName', nx):
                    break
                wl.append(nx)
            win = '\n'.join(wl)
            if re.search(r'\bcontextLoads\b', line):
                continue
            for s in re.findall(r'["\'`](/[^"\'`\s]*)["\'`]', line):
                if TEST_CALL.search(win) and ASSERT.search(win):
                    only401 = ONLY_AUTH.search(win) and not re.search(r'isOk|isCreated|\b20[014]\b|HTTP_20[014]|isNoContent|isBadRequest|isNotFound|\b40[049]\b', win)
                    if not only401:
                        paths.append((norm_path(s.split('?')[0]), p, i))
            for u in re.findall(r'reverse\s*\(\s*[\'"]([\w:-]+)[\'"]', line):
                if ASSERT.search(win):
                    urlnames.add(u.split(':')[-1])
            if ASSERT.search(win):
                for nm in re.findall(r'\b([A-Z]\w*(?:Service|Controller|Handler|Facade|UseCase|Repository|View|ViewSet))\b', line):
                    names[nm] += 1
                for nm in re.findall(r'\.\s*([a-z]\w{2,})\s*\(', line):
                    names['.' + nm] += 1
    return paths, names, urlnames


def path_match(api_path, test_path):
    a = [s for s in api_path.strip('/').split('/') if s]
    b = [s for s in test_path.strip('/').split('/') if s]
    if not a or len(b) < len(a):
        return False
    tail = b[len(b) - len(a):]
    return all(x == '{}' or x == y or (y.startswith('${') or y.startswith('{')) for x, y in zip(a, tail)) and (len(b) - len(a) <= 2)


def api9_cover(rc, api, tix):
    paths, names, urlnames = tix
    if any(path_match(api['path'], tp) for tp, _, _ in paths):
        return True
    h = api['h']
    if not h:
        return False
    if api['fw'] == 'django':
        mk = rc.masks(api['file'])
        if mk:
            line = mk[0].split('\n')[api['line'] - 1] if api['line'] - 1 < len(mk[0].split('\n')) else ''
            un = re.search(r'name\s*=\s*[\'"]([\w-]+)[\'"]', line)
            if un and un.group(1) in urlnames:
                return True
    for g in callees(rc, h, 1, 6):
        cls = g.get('cls')
        if cls and names.get(cls) and names.get('.' + g['name']):
            return True
    return False


# ---------------- API-C1 비밀번호가 응답에 나감
PW_FIELD = re.compile(r'\b(?:private|protected|public)?\s*(?:String|string|str|char\[\])\s+(password|passwd|pwd|userPassword|user_pw|userPw|pw)\b|^\s*(password|hashed_password|passwd|pwd)\s*[:=]', re.M)


def apic1(rc, api, M):
    """-> None(안 걸림) · 'certain' · 'unclear'"""
    h = api['h']
    if not h or not is_rest(rc, api):
        return None
    if api['fw'] == 'spring':
        r = java_ret(h)
        for x in re.findall(r'\b[A-Z]\w*', r):
            c = M.entities.get(x) or (dto_class(rc, x, 'java') if (x in M.dtos and DTO_NAME.search(x)) else None)
            if not c:
                continue
            t = class_text(rc, c)
            mo = PW_FIELD.search(t)
            if mo and not re.search(r'@JsonIgnore\b|WRITE_ONLY|@JsonIgnoreProperties\s*\([^)]*password', t[max(0, mo.start() - 200):mo.end()] + t[:600]):
                return 'certain'
        return None
    if api['fw'] == 'fastapi':
        an = h.get('annos') or ''
        rm = re.search(r'response_model\s*=\s*([\w\[\]., ]+)', an)
        for x in re.findall(r'\b([A-Z]\w*)', rm.group(1) if rm else ''):
            c = M.pyd.get(x) or M.orm.get(x)
            if c and re.search(r'^\s*(password|hashed_password|passwd)\s*:', c.get('code', ''), re.M):
                return 'certain'
        return None
    if api['fw'] == 'django':
        cls = next((c for c in rc.o.classes.get(h.get('cls') or '', []) if c.get('lang') == 'py'), None) if h.get('cls') else None
        text = (cls.get('code', '') if cls else '') + (h.get('code') or '')
        for s in set(re.findall(r'serializer_class\s*=\s*(\w+)', text)) | set(re.findall(r'\b(\w+Serializer)\s*\(', text)):
            sc = M.ser.get(s)
            if not sc:
                continue
            f = sc.get('assigns', {}).get('Meta.fields', '')
            model = sc.get('assigns', {}).get('Meta.model', '')
            wo = re.search(r'[\'"]password[\'"]\s*:\s*\{[^}]*write_only[\'"]?\s*:\s*True|password\s*=\s*serializers\.\w+\([^)]*write_only\s*=\s*True', sc.get('code', ''))
            if not wo and (re.search(r'[\'"]password[\'"]', f) or ('__all__' in f and re.search(r'(?i)user|member|account', model))):
                return 'certain'
        return None
    if api['fw'] in ('express', 'nest'):
        m = h.get('masked') or ''
        if re.search(r'(?i)user|member|account|auth|login|sign', api['path'] + ' ' + api['hfile']):
            rv = returned_vars_js(m) if api['fw'] == 'express' else re.findall(r'\breturn\s+([^;\n]+)', m)
            dbv = db_vars_js(m)
            for x in rv:
                ids = set(re.findall(r'(?<![\w.$])([A-Za-z_$][\w$]*)', x))
                if (ids & dbv or G.TS_DB.search(x)) and re.search(r'(?i)user|member', x) and not re.search(r'select|password|exclude|omit', m):
                    return 'unclear'
    return None


# ======================================================================== 로그 항목
LOGGER_DEF = re.compile(r'LoggerFactory\s*\.\s*getLogger\s*\(|@Slf4j\b|@Log4j2?\b|@CommonsLog\b|LogManager\s*\.\s*getLogger\s*\(|Logger\s*\.\s*getLogger\s*\(|'
                        r'winston\s*\.\s*createLogger\s*\(|createLogger\s*\(|\bpino\s*\(|bunyan\s*\.\s*createLogger|log4js\s*\.\s*getLogger|new\s+Logger\s*\(|'
                        r'logging\s*\.\s*getLogger\s*\(|logging\s*\.\s*basicConfig\s*\(|from\s+loguru\s+import|structlog\s*\.\s*get_logger')
LOG_CALL = re.compile(r'\b(?:log|logger|LOGGER|LOG|_logger|_log|this\s*\.\s*logger|self\s*\.\s*logger|logging|Logger)\s*\.\s*(?:info|debug|warn|warning|error|trace|fatal|log|exception|critical|verbose)\s*\(')
PRINT_CALL = re.compile(r'\bSystem\s*\.\s*(?:out|err)\s*\.\s*print\w*\s*\(|\bconsole\s*\.\s*(?:log|error|warn|info|debug)\s*\(|(?<![\w.])print\s*\(|printStackTrace\s*\(')


def log1_repo(rc):
    defs = rc.scan(rc.bfiles, LOGGER_DEF, 0, False, 5)
    calls_all = rc.scan(rc.bfiles, LOG_CALL, 1, False, 2000)
    my_calls = [x for x in calls_all if rc.mine(x[0], x[1])]
    my_prints = rc.scan(rc.bfiles, PRINT_CALL, 1, True, 2000)
    nest_logger = rc.scan(rc.bfiles, re.compile(r'new\s+Logger\s*\(|Logger\s*\.\s*(?:log|error|warn)\s*\('), 1, False, 1)
    used = bool(defs or nest_logger) and bool(calls_all)
    return dict(used=used, defs=defs[:1], calls=len(calls_all), my_calls=len(my_calls), my_prints=len(my_prints),
                ev=ev(rc, path=(defs or calls_all or [(None, None)])[0][0], line=(defs or calls_all or [(None, None)])[0][1], rule='backend.log.LOG1.logger' + RULE_V) if used else None,
                trace=(my_prints[0][:2] if my_prints else None))


def catches(rc):
    """내 catch·except 블록 -> [dict(path, line, broad, empty, comment_only, ok)]"""
    out = []
    for p in rc.bfiles:
        m = rc.masks(p)
        if not m:
            continue
        nc, mk = m
        raw = rc.text(p) or ''
        if p.endswith('.py'):
            lines = mk.split('\n')
            rlines = raw.split('\n')
            for i, line in enumerate(lines, 1):
                mo = re.match(r'^(\s*)except\b\s*([^:]*):\s*(.*)$', line)
                if not mo or not rc.mine(p, i):
                    continue
                ind = len(mo.group(1))
                body, body_raw = [], []
                if mo.group(3).strip():
                    body.append(mo.group(3).strip())
                j = i
                while j < len(lines):
                    nx = lines[j]
                    if nx.strip() and (len(nx) - len(nx.lstrip())) <= ind:
                        break
                    if nx.strip():
                        body.append(nx.strip())
                    if j < len(rlines) and rlines[j].strip():
                        body_raw.append(rlines[j].strip())
                    j += 1
                code_body = [b for b in body if b not in ('pass', '...')]
                exc = mo.group(2).strip()
                broad = exc == '' or bool(re.search(r'\b(?:Exception|BaseException)\b', exc))
                bj = '\n'.join(body)
                keep = bool(re.search(r'\braise\b|logger?\s*\.\s*exception\s*\(|exc_info\s*=\s*True|traceback\.|logging\.exception|\.error\s*\([^)]*(?:\be\b|exc|err|error)\b|capture_exception', bj))
                empty = not code_body
                comment_only = empty and any(b.startswith('#') for b in body_raw)
                out.append(dict(path=p, line=i, broad=broad, empty=empty, comment_only=comment_only, keep=keep))
        else:
            for mo in re.finditer(r'\bcatch\s*(\(([^)]*)\))?\s*\{', mk):
                ln = rc.li(p).line(mo.start())
                if not rc.mine(p, ln):
                    continue
                b = mo.end() - 1
                e = oc.match(mk, b, '{', '}')
                body = mk[b + 1:e]
                exc = nc[mo.start(2):mo.end(2)] if mo.group(2) else ''
                java = p.endswith(('.java', '.kt'))
                broad = (not java) or bool(re.search(r'\b(?:Exception|Throwable|RuntimeException)\b', exc))
                var = (re.findall(r'(\w+)\s*$', exc.strip()) or [''])[0] if exc else ''
                keep = bool(re.search(r'\bthrow\b', body)) and (not java or bool(re.search(r'throw\s+\w+\s*;|throw\s+new\s+\w+\s*\([^;]*\b' + re.escape(var or 'e') + r'\b', body))) if var or not java else bool(re.search(r'\bthrow\b', body))
                if not keep and var:
                    keep = bool(re.search(r'(?:log|logger|LOGGER|LOG)\s*\.\s*(?:error|warn|info|debug|fatal)\s*\([^;]*\b' + re.escape(var) + r'\b[^;]*\)', body)) or \
                        bool(re.search(r'\bnext\s*\(\s*' + re.escape(var) + r'\b', body)) or bool(re.search(r'\breject\s*\(\s*' + re.escape(var), body))
                empty = not body.strip()
                comment_only = empty and bool(re.search(r'//|/\*', (rc.text(p) or '')[b + 1:e]))
                out.append(dict(path=p, line=ln, broad=broad, empty=empty, comment_only=comment_only, keep=keep))
    return out


def global_500_log(rc):
    """전역 처리기가 500을 스택과 함께 error 로그 -> (ok, ev, where)"""
    o = rc.o
    for name, cl in o.classes.items():
        for c in cl:
            if c['file'] not in rc.bset:
                continue
            if c.get('lang') == 'java' and re.search(r'@(?:Rest)?ControllerAdvice\b', c.get('annos') or ''):
                txt = class_text(rc, c)
                ok = bool(re.search(r'@ExceptionHandler\s*\(\s*(?:\{?\s*)?(?:Exception|Throwable|RuntimeException)\.class', txt)) and \
                    bool(re.search(r'(?:log|logger|LOGGER|LOG)\s*\.\s*error\s*\([^;]*,\s*\w+\s*\)\s*;', txt))
                ln = rc.li(c['file']).line(c['start'])
                if ok:
                    return True, ev(rc, path=c['file'], line=ln, rule='backend.log.LOG2.spring.advice-500' + RULE_V), (c['file'], ln)
                return False, None, (c['file'], ln)
            if c.get('lang') == 'ts' and re.search(r'@Catch\s*\(\s*\)', c.get('annos') or ''):
                txt = class_text(rc, c)
                ok = bool(re.search(r'logger\s*\.\s*error\s*\([^;]*(?:stack|exception|error)', txt))
                ln = rc.li(c['file']).line(c['start'])
                return ok, (ev(rc, path=c['file'], line=ln, rule='backend.log.LOG2.nest.catch-all' + RULE_V) if ok else None), (c['file'], ln)
    for p in rc.bfiles:
        m = rc.masks(p)
        if not m:
            continue
        nc, mk = m
        if p.endswith(('.js', '.ts', '.mjs', '.cjs')):
            for mo in re.finditer(r'\(\s*(err|error|e)\s*(?::\s*\w+)?\s*,\s*(?:req|request)\s*(?::\s*\w+)?\s*,\s*(?:res|response)\s*(?::\s*\w+)?\s*,\s*next\s*(?::\s*\w+)?\s*\)\s*(?:=>)?\s*\{', mk):
                b = mo.end() - 1
                body = nc[b:oc.match(mk, b, '{', '}')]
                ln = rc.li(p).line(mo.start())
                ok = bool(re.search(r'(?:logger|log|winston|pino)\s*\.\s*error\s*\([^)]*' + mo.group(1) + r'\b', body))
                return ok, (ev(rc, path=p, line=ln, rule='backend.log.LOG2.express.error-mw' + RULE_V) if ok else None), (p, ln)
        if p.endswith('.py'):
            mo = re.search(r'exception_handler\s*\(\s*Exception\s*\)|add_exception_handler\s*\(\s*Exception', mk)
            if mo:
                ln = rc.li(p).line(mo.start())
                ok = bool(re.search(r'logger?\s*\.\s*exception\s*\(|exc_info\s*=\s*True', nc[mo.start():mo.start() + 1500]))
                return ok, (ev(rc, path=p, line=ln, rule='backend.log.LOG2.py.handler-500' + RULE_V) if ok else None), (p, ln)
    return False, None, None


REQLOG_TIME = re.compile(r'currentTimeMillis|nanoTime|StopWatch|Instant\s*\.\s*now|Date\s*\.\s*now|performance\s*\.\s*now|process\s*\.\s*hrtime|time\s*\.\s*(?:time|perf_counter|monotonic)\s*\(')
REQLOG_PATH = re.compile(r'getRequestURI|getServletPath|getRequestURL|req(?:uest)?\s*\.\s*(?:url|originalUrl|path|baseUrl)\b|request\s*\.\s*(?:path|url\s*\.\s*path|get_full_path|url)\b|scope\s*\[\s*[\'"]path')
REQLOG_STATUS = re.compile(r'getStatus\s*\(|res(?:ponse)?\s*\.\s*statusCode|response\s*\.\s*status_code|\.status_code|statusCode')
MW_SHAPE = re.compile(r'implements\s+(?:Filter|HandlerInterceptor|NestInterceptor|NestMiddleware|WebFilter)|extends\s+(?:OncePerRequestFilter|GenericFilterBean|HandlerInterceptorAdapter|BaseHTTPMiddleware|MiddlewareMixin)|'
                      r'@\w+\s*\.\s*middleware\s*\(\s*[\'"]http|def\s+__call__\s*\(\s*self\s*,\s*request|process_response\s*\(|\(\s*req\w*\s*(?::\s*\w+)?\s*,\s*res\w*\s*(?::\s*\w+)?\s*,\s*next\s*(?::\s*\w+)?\s*\)|'
                      r'res\s*\.\s*on\s*\(\s*[\'"]finish|@Aspect|after_request|before_request')
LIB_REQLOG = re.compile(r'\bmorgan\s*\(\s*([\'"](\w+)[\'"]|[\'"][^\'"]*:response-time)|pinoHttp\s*\(|pino-http|expressWinston\s*\.\s*logger|express-winston|server\.tomcat\.accesslog\.enabled\s*[:=]\s*true|'
                       r'accesslog[\s\S]{0,200}pattern[^\n]*%[DT]')


def log3_repo(rc):
    own_hits, lib_hits = [], []
    for p in rc.bfiles:
        m = rc.masks(p)
        if not m:
            continue
        nc, mk = m
        if MW_SHAPE.search(mk) and REQLOG_TIME.search(mk) and REQLOG_PATH.search(nc) and REQLOG_STATUS.search(mk) and (LOG_CALL.search(mk) or re.search(r'\.info\s*\(|\.log\s*\(', mk)):
            mo = REQLOG_TIME.search(mk)
            ln = rc.li(p).line(mo.start())
            if rc.mine(p, ln) or (rc.mine_ratio(p) or 0) > 0.5:
                own_hits.append((p, ln))
    for p in rc.bfiles + rc.configs():
        m = rc.masks(p)
        if not m:
            continue
        for mo in LIB_REQLOG.finditer(m[0]):
            fmt = mo.group(2) or ''
            if fmt and fmt in ('combined', 'common'):
                continue
            ln = rc.li(p).line(mo.start())
            if rc.mine(p, ln) or (p in rc.configs() and (rc.mine_ratio(p) or 0) > 0.5):
                lib_hits.append((p, ln))
    trace = rc.scan(rc.bfiles, re.compile(r'OncePerRequestFilter|HandlerInterceptor|NestInterceptor|morgan|middleware|MiddlewareMixin|@Aspect'), 1, True, 1)
    return own_hits, lib_hits, (trace[0][:2] if trace else None)


LOG_LEVEL_CFG = re.compile(r'(?i)logging\.level|^\s*level\s*:|<root\s+level|<logger\s+[^>]*level|\blevel\s*=\s*["\']?(?:INFO|WARN|ERROR|DEBUG)|[\'"]level[\'"]\s*:\s*[\'"]?(?:INFO|WARN|ERROR|DEBUG)|'
                           r'setLevel\s*\(|level\s*:\s*[\'"](?:info|warn|error|debug|http)[\'"]|LOG_LEVEL|rootLogger\.level', re.M)
LOG_KEEP_CFG = re.compile(r'(?i)maxHistory|max-history|max_history|RollingFileAppender|TimeBasedRollingPolicy|SizeAndTimeBasedRollingPolicy|logging\.file\.(?:name|path)|'
                          r'RotatingFileHandler|TimedRotatingFileHandler|backupCount|DailyRotateFile|maxFiles|max-file|max_size|max-size|logging\s*:\s*\n\s*driver|'
                          r'awslogs|fluentd|gelf|loki|log-driver|daysToKeep|numBackups')


def log4_repo(rc):
    hits = []
    for p in rc.configs() + rc.bfiles:
        t = (rc.masks(p) or ('', ''))[0]
        if not t:
            continue
        lv, kp = LOG_LEVEL_CFG.search(t), LOG_KEEP_CFG.search(t)
        if lv or kp:
            mine = (rc.mine_ratio(p) or 0) > 0.5 if p not in rc.bset else rc.mine(p, rc.li(p).line((kp or lv).start()))
            prod = not re.search(r'(?i)(^|[-_.])(dev|local|test)([-_.]|$)', p.rsplit('/', 1)[-1])
            hits.append(dict(path=p, line=rc.li(p).line((kp or lv).start()), level=bool(lv), keep=bool(kp), mine=mine, prod=prod))
    lv = [h for h in hits if h['level'] and h['mine'] and h['prod']]
    kp = [h for h in hits if h['keep'] and h['mine'] and h['prod']]
    return lv, kp, hits


TRACE_SET = re.compile(r'MDC\s*\.\s*put\s*\(|ThreadContext\s*\.\s*put\s*\(|AsyncLocalStorage|\.run\s*\(\s*\{[^}]*(?:requestId|traceId)|cls-hooked|ClsModule|nestjs-cls|'
                       r'ContextVar\s*\(|\w+_id_var\s*\.\s*set\s*\(|correlation_id|CorrelationIdMiddleware|asgi_correlation_id|X-Request-ID|x-request-id|genReqId|request_id_var')
TRACE_FMT = re.compile(r'%X\{|%mdc|%\(\w*(?:request|trace|correlation)_?id\)s|requestId|traceId|correlation_id|request_id|\{request_id\}|reqId', re.I)


def log5_repo(rc):
    sets = rc.scan(rc.bfiles, TRACE_SET, 0, True, 5)
    fmts = []
    for p in rc.configs() + rc.bfiles:
        t = (rc.masks(p) or ('', ''))[0]
        if not t:
            continue
        for mo in re.finditer(r'(?im)^.*(?:pattern|format|fmt|formatter).*$', t):
            if TRACE_FMT.search(mo.group(0)):
                ln = rc.li(p).line(mo.start())
                mine = rc.mine(p, ln) or (p not in rc.bset and (rc.mine_ratio(p) or 0) > 0.5)
                fmts.append((p, ln, mine))
                break
    trace = rc.scan(rc.bfiles + rc.configs(), re.compile(r'(?i)traceId|requestId|request_id|correlation|MDC|sleuth|micrometer-tracing|opentelemetry'), 0, False, 1)
    return sets, fmts, (trace[0][:2] if trace else None)


LOGC1_ARG = re.compile(r'(?i)(?<![\w.])(?:password|passwd|pwd|rawPassword|plainPassword|accessToken|refreshToken|access_token|refresh_token|jwtToken|jwt|token|secret|apiKey|api_key|clientSecret|authorization)\b(?!\s*(?:Provider|Service|Util|Encoder|Repository|Manager|Filter|Validator|Expir|Type|Length|Header|Name|Prefix|Store)\w*)|'
                       r'\.get(?:Password|AccessToken|RefreshToken|Token|Secret)\s*\(\s*\)|\breq\s*\.\s*body\s*\.\s*(?:password|token)|\bheaders\s*\[\s*[\'"]authorization|getHeader\s*\(\s*[\'"]Authorization')
LOGC1_BODY = re.compile(r'(?i)\breq\s*\.\s*body\s*\)|JSON\s*\.\s*stringify\s*\(\s*req\s*\.\s*body')


def logc1_repo(rc):
    certain, unclear = [], []
    for p in rc.bfiles:
        m = rc.masks(p)
        if not m:
            continue
        nc, mk = m
        for mo in re.finditer(LOG_CALL.pattern + r'|' + PRINT_CALL.pattern, mk):
            ln = rc.li(p).line(mo.start())
            if not rc.mine(p, ln):
                continue
            q = mo.end() - 1
            e = oc.match(mk, q, '(', ')')
            args = mk[q:e + 1]
            if LOGC1_ARG.search(args):
                certain.append((p, ln))
            elif LOGC1_BODY.search(args) and re.search(r'(?i)auth|login|sign|user|member|password', p):
                unclear.append((p, ln))
    return certain, unclear


# ======================================================================== 부가 기술 영역 EXT1~4(A-2.7)
EXT_RX = {
    'EXT1': re.compile(r'\bAmazonS3(?:Client)?\b\s*\.\s*\w+|\bS3Client\b[\s\S]{0,40}?\.\s*(?:builder|create)|\bs3Client\s*\.\s*\w+\s*\(|S3AsyncClient|PutObjectCommand|PutObjectRequest|\.putObject\s*\(|upload_fileobj\s*\(|'
                       r'boto3\s*\.\s*(?:client|resource)\s*\(\s*["\']s3|multerS3\s*\(|multer-s3|\bcloudinary\s*\.\s*(?:uploader|v2)\b|firebase_admin\s*\.\s*storage|\bMinioClient\b|new\s+Minio\s*\.\s*Client|'
                       r'generatePresignedUrl|generate_presigned_url|S3Presigner|S3Template|AWS_STORAGE_BUCKET_NAME\s*=|storages\.backends\.s3|getSignedUrl\s*\(|\.upload_file\s*\(|'
                       r'storage\s*\.\s*Client\s*\(\s*\)|\.bucket\s*\(\s*[\w\'"]+\s*\)\s*\.\s*(?:file|blob)\s*\('),
    'EXT2': re.compile(r'@EnableWebSocket(?:MessageBroker)?\b|WebSocketConfigurer|WebSocketMessageBrokerConfigurer|@ServerEndpoint|SimpMessagingTemplate|@MessageMapping|TextWebSocketHandler|'
                       r'\bio\s*\.\s*on\s*\(\s*["\']connection|new\s+(?:socketio\s*\.\s*)?Server\s*\([^)]*\)[\s\S]{0,400}\.on\s*\(\s*["\']connection|new\s+WebSocket\s*\.\s*Server|new\s+WebSocketServer\s*\(|'
                       r'@WebSocketGateway|@SubscribeMessage|(?:Async)?(?:Json)?WebsocketConsumer|@\w+\s*\.\s*websocket\s*\(|CHANNEL_LAYERS\s*=|socketio\s*\.\s*(?:Async)?Server\s*\(|\bSocketIO\s*\(\s*app'),
    'EXT2_SSE': re.compile(r'\bSseEmitter\b|EventSourceResponse|text/event-stream|MediaType\s*\.\s*TEXT_EVENT_STREAM'),
    'EXT3': re.compile(r'@Operation\s*\(|@Tag\s*\(\s*name|@ApiOperation\s*\(|@Api\s*\(\s*(?:tags|value)|@EnableSwagger2|new\s+OpenAPI\s*\(|\bGroupedOpenApi\b|new\s+Docket\s*\(|'
                       r'SwaggerModule\s*\.\s*(?:setup|createDocument)|new\s+DocumentBuilder\s*\(|swaggerUi\s*\.\s*(?:serve|setup)|swaggerJSDoc\s*\(|swaggerJsdoc\s*\(|get_schema_view\s*\(|'
                       r'Spectacular(?:API|Swagger|Redoc)View|SPECTACULAR_SETTINGS\s*=|@ApiProperty\s*\(|@ApiTags\s*\(|@extend_schema|swagger_auto_schema|openapi_tags\s*=|@OpenAPIDefinition|'
                       r'^\s*springdoc\s*:|^springdoc\.|docs_url\s*=\s*["\'][^"\']+["\']|openapi_url\s*=\s*["\']', re.M),
    'EXT4': re.compile(r'kauth\.kakao\.com|kapi\.kakao\.com|nid\.naver\.com|openapi\.naver\.com/v1/nid|accounts\.google\.com|oauth2\.googleapis\.com|googleapis\.com/oauth2|googleapis\.com/userinfo|'
                       r'github\.com/login/oauth|api\.github\.com/user|appleid\.apple\.com|oauth2\s*[.:]\s*client\s*[.:]\s*(?:registration|provider)|registration\s*:\s*\n\s*(?:kakao|naver|google|github|apple)\s*:|'
                       r'(?:Kakao|Google|Naver|Github|GitHub|Apple)Strategy\b|passport\s*\.\s*authenticate\s*\(\s*["\'](?:kakao|google|naver|github|apple)|\bverifyIdToken\s*\(|verify_oauth2_token|'
                       r'OAuth2UserService|\.oauth2Login\s*\(|allauth\.socialaccount\.providers\.\w+|SOCIALACCOUNT_PROVIDERS\s*='),
}
EXT_DEP = {
    'EXT1': re.compile(r'(?i)aws-sdk|@aws-sdk/client-s3|spring-cloud-aws|spring-cloud-starter-aws|awssdk|software\.amazon\.awssdk|boto3|django-storages|multer-s3|cloudinary|minio|firebase-admin|google-cloud-storage'),
    'EXT2': re.compile(r'(?i)spring-boot-starter-websocket|socket\.io|"ws"\s*:|@nestjs/websockets|@nestjs/platform-socket\.io|channels|python-socketio|flask-socketio|websockets'),
    'EXT3': re.compile(r'(?i)springdoc|springfox|swagger|@nestjs/swagger|drf-spectacular|drf-yasg|flasgger|fastapi'),
    'EXT4': re.compile(r'(?i)oauth2-client|spring-boot-starter-oauth2|passport-kakao|passport-google|passport-naver|passport-github|django-allauth|social-auth|authlib|google-auth|kakao'),
}
EXT_NAME = {'EXT1': '파일 저장소', 'EXT2': '실시간 통신', 'EXT3': 'API 문서', 'EXT4': '소셜 로그인'}


def ext_scan(repo, rc, paths, mine_only):
    """-> {EXT: [(path, line)]}, sse hits, default_on"""
    res = {k: [] for k in EXT_NAME}
    sse, dflt = [], []
    for p in paths:
        if rc is not None:
            m = rc.masks(p)
            li = rc.li(p)
            mn = (lambda ln, p=p: rc.mine(p, ln))
        else:
            t = repo.text(p)
            if t is None:
                continue
            m = mask_py(t) if p.endswith('.py') else oc.strip_c(t) if re.search(r'\.(java|kt|js|jsx|ts|tsx|mjs|cjs)$', p) else (t, t)
            li = LineIdx(m[0])
            own = repo.own_line_set(p)
            mn = (lambda ln, own=own: bool(own) and ln in own)
        if not m:
            continue
        nc, mk = m
        nlines = nc.split('\n')
        for k, rx in EXT_RX.items():
            src = nc if k in ('EXT4', 'EXT3', 'EXT1') else mk
            for mo in rx.finditer(src):
                ln = li.line(mo.start())
                cur = nlines[ln - 1] if ln - 1 < len(nlines) else ''
                if re.match(r'\s*(?:import|from|require)\b', cur) or re.search(r'require\s*\(\s*[\'"]', cur):
                    continue
                if re.search(r'(?i)enabled\s*[:=]\s*false', '\n'.join(nlines[ln - 1:ln + 3])):
                    continue
                if mine_only and not mn(ln):
                    continue
                if k == 'EXT2_SSE':
                    sse.append((p, ln))
                else:
                    res[k].append((p, ln))
                break
    return res, sse, dflt


def ext_default_on(rc):
    """기본값으로 켜짐(「제안」 [B-42]): springdoc 의존성만, FastAPI 기본 /docs."""
    out = []
    for p, t in (rc.ctx.get('build_texts') or {}).items():
        if re.search(r'springdoc-openapi', t or ''):
            out.append(('springdoc 의존성', p))
    if 'fastapi' in rc.fws:
        out.append(('FastAPI 기본 /docs', None))
    return out


# ======================================================================== LOG6 원인 찾은 기록(A-2.5)
def log6_candidates(repo, loose=False):
    prs = {p.get('number'): p for p in repo.prs}
    by_pr = collections.defaultdict(list)
    for c in repo.commits:
        if c.get('pr'):
            by_pr[c['pr']].append(c)
    out = []
    for c in repo.own_commits:
        msg = (c.get('subject') or '') + '\n' + (c.get('body') or '')
        if not (FIX_STRICT.search(msg) or (loose and FIX_LOOSE.search(msg))):
            continue
        tfiles = [f['path'] for f in c['files'] if L.TEST.search(f['path'])]
        pr = prs.get(c.get('pr')) if c.get('pr') else None
        pr_tests = []
        if c.get('pr'):
            for c2 in by_pr[c['pr']]:
                pr_tests += [f['path'] for f in c2['files'] if L.TEST.search(f['path'])]
        docs = [f['path'] for f in c['files'] if DOC_EXT.search(f['path'])]
        out.append(dict(sha=c['sha'], date=c['date_kst'], test_in_commit=bool(tfiles), test_in_pr=bool(pr_tests), tests=sorted(set(tfiles + pr_tests))[:6],
                        cause_word=bool(CAUSE.search(msg) or (pr and CAUSE.search((pr.get('title') or '') + (pr.get('body') or '')))),
                        pr=c.get('pr'), pr_body=bool(pr and (pr.get('body') or '').strip()), docs=docs[:4], strict=bool(FIX_STRICT.search(msg))))
    return out


# ======================================================================== S5 질문 틀
GUIDE_COMMON = ('너는 신입 백엔드 개발자의 공개 레포 코드를 읽고 「문서」(백엔드 LV 기준 v5) 항목 하나를 판정한다. 판정 기준은 아래 문서 문구와 사용자 결정 그대로다. '
                '공통 규칙: 작동하는 것만 인정한다(선언만 있고 연결이 없으면 아니오: 활성화 설정 없는 어노테이션, 기본값만 있는 타임아웃 등). '
                '근거는 코드·설정 파일·배포 스크립트만이다(README·문서의 주장은 근거가 아니다). 분모·분자 모두 이 사람의 코드(앞에 * 표시된 줄)로 본다. '
                'yes의 근거는 보여 준 자료 안의 이 사람 줄이어야 한다.')
S5_TEMPLATES = {
    'API3.input_check': dict(
        system=GUIDE_COMMON + '\n항목 API3 입력 검사(「문서」): 입력 받는 API(파일 업로드 포함)에 길이·범위·형식·크기 검사가 작동하게 연결. '
               '타입 선언만 있고 제약이 없으면 검사가 아니다(「제안」). 손으로 쓴 검사(길이 비교·형식 검사 후 400 오류·예외)도 이 API의 요청 흐름에서 실제로 실행되면 검사로 본다.',
        question='이 API가 받는 입력(본문·쿼리·파일)에 길이·범위·형식·크기 검사가 실제로 작동하게 연결되어 있는가? yes = 입력 대부분(본문·파일은 반드시)에 작동하는 검사가 있음, no = 검사가 없거나 연결이 안 됨. value는 null.'),
    'API4.response_shape': dict(
        system=GUIDE_COMMON + '\n항목 API4 필요한 값만 응답(「문서」): DB 모델을 그대로 반환하지 않고 응답 모양을 따로 정함(응답 DTO, 필드를 골라 새 객체로, serializer fields 명시(__all__ X), response_model).',
        question='이 API가 DB 모델(엔티티·ORM 객체·DB 행)을 그대로 응답으로 내보내는가, 응답 모양을 따로 정해 내보내는가? yes = 응답 모양을 따로 정함(필요한 값만), no = DB 모델을 그대로 반환(목록·감싼 객체 안에 넣어도 그대로면 no). '
                 'DB 데이터를 돌려주지 않는 API(메시지·void)면 decision=no, value="nodata". value는 그 밖에는 null.'),
    'API7.external_call': dict(
        system=GUIDE_COMMON + '\n항목 API7 외부 API(「문서」): 외부 서비스(결제·메일·지도·AI·파일 저장소)를 부르는 곳에 직접 설정한 타임아웃 + 실패 처리(오류 응답·재시도). 기본값만이면 아니오(규칙 6). 우리 서버끼리의 호출은 대상이 아니다.',
        question='이 외부 호출 지점에 (1) 직접 설정한 타임아웃(호출 인자·이 호출이 쓰는 클라이언트 설정·설정 파일)과 (2) 실패 처리(try/catch로 오류 응답·로그, 재시도 설정)가 둘 다 있는가? yes = 둘 다, no = 하나라도 없음. '
                 '이 호출이 외부 서비스가 아니면(우리 서버) decision=no, value="internal".'),
    'API8.cache': dict(
        system=GUIDE_COMMON + '\n항목 API8 캐시(가점형, 「문서」): 만료 시간 + 우리 DB 데이터면 바뀔 때 삭제(외부 응답 캐시는 만료 시간만) + 작동 연결. 제대로 했을 때만 점수에 넣는다. 토큰·인증 코드 저장은 캐시가 아니다(「제안」).',
        question='이 레포의 캐시가 (1) 만료 시간 (2) 캐시한 값이 우리 DB 데이터면 데이터를 고치는 경로에서 삭제(외부 응답이면 불필요) (3) 작동 연결(활성화)을 모두 갖추었는가? yes = 모두 갖춤, no = 하나라도 없음 또는 캐시가 아님. value는 "db" 또는 "external" 또는 null.'),
    'API9.test_cover': dict(
        system=GUIDE_COMMON + '\n항목 API9 테스트(「문서」): 실질 API의 절반 이상을 내 테스트(API 테스트 또는 그 API가 부르는 서비스 테스트)가 다룸. 결과를 단언하는 테스트만 센다(자동 생성 contextLoads 등 제외). 401·403만 단언하는 테스트는 세지 않는다(규칙 7).',
        question='이 API(또는 이 API가 부르는 서비스 메서드)를 이 사람의 테스트가 부르고 결과를 단언하는가? yes = 다룸, no = 다루지 않음.'),
    'API-C1.password_response': dict(
        system=GUIDE_COMMON + '\n상한 API-C1(「문서」): 비밀번호(해시 포함)가 응답에 나감 → API 변수 최대 2. 확실할 때만 건다(「제안」). 직렬화 제외(@JsonIgnore·serializer fields·select 제외·write_only)가 있으면 나가지 않는다.',
        question='이 API의 응답으로 비밀번호(해시 포함) 칸이 실제로 나가는가? yes = 나감(확실), no = 나가지 않음.'),
    'LOG2.exception_log': dict(
        system=GUIDE_COMMON + '\n항목 LOG2 예외 로그(「문서」): 빈 catch 0개 + 특정 예외만 골라 처리하고 나머지는 원인 보존 재던짐 또는 스택 로그 + 전역 처리기가 500을 스택과 함께 error 로그. 세 조건 모두(한 레포 안).',
        question='이 레포에서 세 조건(빈 catch 없음, 넓은 예외는 원인 보존 재던짐 또는 스택 로그, 전역 처리기가 500을 스택과 함께 error 로그)을 모두 채우는가? yes = 모두, no = 하나라도 아님.'),
    'LOG3.request_log': dict(
        system=GUIDE_COMMON + '\n항목 LOG3 요청 로그(「문서」): 요청마다 경로·상태 코드·처리 시간을 미들웨어·필터 한 곳에서 기록.',
        question='이 레포에 요청마다 경로·상태 코드·처리 시간 셋을 한 곳(미들웨어·필터·인터셉터 또는 그런 라이브러리 설정)에서 기록하는 코드가 있는가? yes/no.'),
    'LOG4.log_config': dict(
        system=GUIDE_COMMON + '\n항목 LOG4 로그 설정(「문서」): 운영 로그 레벨 + 보관(파일·보관 기간, 또는 stdout + 로그 드라이버). 운영 설정 = 배포 근거가 실제로 읽는 설정(프로필이 하나면 그 설정). 공용 설정 파일은 이 사람 줄이 과반일 때만.',
        question='이 레포의 운영 설정에 로그 레벨과 보관(파일 롤링·보관 기간, 또는 stdout + compose 로그 드라이버)이 둘 다 정해져 있는가? yes/no.'),
    'LOG5.trace_id': dict(
        system=GUIDE_COMMON + '\n항목 LOG5 요청 추적 ID(「문서」): 요청마다 ID를 붙여 그 요청의 모든 로그에 남김(MDC·AsyncLocalStorage·contextvars + 로그 형식에 ID).',
        question='요청이 들어올 때마다 ID를 만들어 넣고(필터·미들웨어), 로그 형식(패턴·포매터)이 그 ID를 모든 로그에 찍는가? yes = 둘 다, no = 하나라도 없음.'),
    'LOG6.cause_record': dict(
        system=('너는 커밋 하나를 판정한다. 「문서」 백엔드 v5 로그 항목 LOG6 원인 찾은 기록 [AI 확인]: 버그 수정 커밋에 원인 + 같은 커밋·PR에 회귀 테스트. '
                '「사용자 결정(2026-11-25)」: 원인이 커밋 메시지·PR 설명에 있거나, 같은 커밋에서 바꾼 문서(.md 등)에 있으면 인정한다. 그 글은 그 버그의 원인이어야 한다(일반 설계 설명은 안 됨). '
                '버그 수정의 정의: 잘못 동작하던 것을 고친 커밋. 기능 추가·문서·스타일·리팩터링·설정 변경만이면 버그 수정이 아니다(제목에 fix가 있어도 기능 추가면 아니다). '
                '원인: 그 버그가 왜 생겼는지(무엇이 잘못되어 그 증상이 났는지). 증상만 적었거나 무엇을 바꿨는지만 적었으면 원인이 아니다. 문서는 그 커밋이 더한 줄만 본다. '
                '회귀 테스트: 같은 커밋 또는 같은 PR에 그 버그가 다시 생기면 실패할 테스트가 들어감(그 버그와 관계없는 테스트는 아니다).'),
        question='세 칸을 본다: is_bugfix·cause_stated(+cause_where: message·pr·doc)·regression_test. 셋 다 yes면 decision=yes, 하나라도 no면 decision=no. '
                 'value = {"is_bugfix": "yes|no|unclear", "cause_stated": "yes|no|unclear", "cause_where": "message|pr|doc|none", "regression_test": "yes|no|unclear"}. 근거는 sha:앞8자, pr:#번호, 문서·테스트 경로:줄.'),
    'LOG-C1.secret_log': dict(
        system=GUIDE_COMMON + '\n상한 LOG-C1(「문서」): 비밀번호·토큰을 로그에 남김 → 로그 변수 최대 2. 확실할 때만 건다(「제안」). 로그 호출 인자에 비밀번호·토큰·secret·Authorization 값이나 그것이 든 요청 본문 전체가 들어가면 남김이다.',
        question='표시한 로그 호출이 비밀번호·토큰(또는 그것이 든 요청 본문 전체)을 실제로 로그에 남기는가? yes = 남김(확실), no = 남기지 않음(그 요청에 비밀번호·토큰이 없음 포함).'),
    'EXT.area': dict(
        system=('「문서」 백엔드 v5 부가 기술 영역(가점 재료): 파일 저장소(S3 등)·실시간 통신(WebSocket 등)·API 문서(Swagger 등)·소셜 로그인(카카오·구글 등). '
                '썼다고 보는 기준(lv-calc 공통 규칙 8): 이 사람 코드에서 실제로 호출한 곳 1곳 이상, 또는 설정 파일에 그 기능이 쓰이도록 적혀 있음(주석·끄는 값·예시 파일이면 아님). 의존성 파일이나 import 줄에만 있으면 아님. '
                '「제안」: 서버 쪽 코드만 본다(화면 SDK만 있는 소셜 로그인, 클라이언트 SSE는 아님). 프레임워크 기본값으로만 켜지는 것(의존성만 있는 springdoc, FastAPI 기본 /docs)은 아님.'),
        question='이 레포에서 이 영역(대상의 var)을 이 사람 코드가 실제로 쓰는가? yes = 호출·켜는 설정이 이 사람 줄에 있음, no = 없음(의존성·import만 포함).'),
    'GEN.no_trace': dict(
        system=GUIDE_COMMON + '\n규칙이 흔적을 하나도 찾지 못한 항목을 다시 본다(사용자 결정 2026-11-26: 흔적 없는 0을 다시 볼지 두 방식을 돌려 보고 정함). 보여 준 파일 밖은 need로 요청한다.',
        question='rule_result에 적힌 항목의 판정 기준을 이 레포의 이 사람 코드가 채우는 근거가 있는가? yes = 근거 있음(경로:줄), no = 보여 준 자료와 요청한 자료에서 근거가 없음.'),
}


# ======================================================================== 추출
def _item(name, points, value, state, unit='점', ratio=None, ev_=None, notes=None, by_repo=None, definition='', role='item', inst=None, alt=None):
    d = dict(name=name, role=role, value=value, state=state, unit=unit, max=points, by_repo=by_repo or {}, instances=(inst or [])[:300],
             evidence=(ev_ or [])[:20], definition=definition, notes=notes or '')
    if ratio:
        d['ratio'] = ratio
    if alt:
        d['alt'] = alt
    return d


def half_pass(num, den):
    if den == 0:
        return None
    return num == den if den <= 2 else num * 2 >= den


def extract(person):
    t0 = time.time()
    gate = G.gate(person)
    rcs = []
    for r in person.repos:
        g = gate.get(r.key) or {}
        if g.get('pass'):
            rcs.append(RC(r, g))
    data = dict(category=CAT, pid=person.pid, variables={}, s5_targets=[], definition_choices=[], stats={},
                gate=dict(passed=[rc.key for rc in rcs], by_repo={k: dict(passed=v.get('pass'), framework=v.get('framework'), reason=v.get('fail_reason'), state=v.get('state'))
                                                              for k, v in gate.items()}),
                parser=PARSER_NOTE)
    T = data['s5_targets']
    tn = collections.Counter()

    def target(var, rc, template, files=None, commits=None, text=None, rule_result=None, trace='has_trace', priority=5, group=None, stop_rule=None, unit=None):
        tn[var] += 1
        tid = f'{person.pid}.{CAT}.{var}.{tn[var]}'
        T.append(dict(target_id=tid, var=var, repo=rc.key if rc else None, template=template,
                      material=dict(files=files or [], commits=commits or [], **({'text': text[:600]} if text else {})),
                      rule_result=rule_result, trace=trace, priority=priority, group=group, stop_rule=stop_rule, unit=unit))
        return tid

    V = data['variables']
    if not rcs:
        for vid, nm in (('backend.api', 'API·외부 API·캐시'), ('backend.log', '로그')):
            V[vid] = _item(nm, None, 0, 'value_rule', unit='LV(0~5)', role='backend_var', definition='「문서」 규칙 1: 게이트를 통과한 백엔드 레포가 없으면 백엔드 LV 0',
                           notes='게이트 통과 레포 0개(백엔드 LV 0, 판정 불가와 다름)')
        _ext_all_repos(person, data, None)
        data['stats']['seconds'] = round(time.time() - t0, 1)
        return data

    # ---------------- API 목록
    apis = []
    for rc in rcs:
        try:
            apis += build_apis(rc)
        except Exception as e:
            data['stats'].setdefault('errors', []).append(f'{rc.key}: build_apis {repr(e)[:120]}')
    rc_of = {rc.key: rc for rc in rcs}
    models = {rc.key: RepoModel(rc) for rc in rcs}
    sub = [a for a in apis if not a['health']]
    my = [a for a in sub if a['mine']]
    unknown_mine = [a for a in sub if a['mine'] is None]
    data['stats']['apis'] = dict(all=len(apis), substantive=len(sub), mine_A=len(my), mine_B=sum(1 for a in sub if a['mine_def']), mine_C=sum(1 for a in sub if a['mine_any']),
                                 mine_unknown=len(unknown_mine), auto_drf=sum(1 for a in my if a['auto']), by_fw=dict(collections.Counter(a['fw'] for a in my)))

    def inst(a, status, what):
        return dict(repo=a['repo'], path=a['hfile'], line=a['hstart'], what=f"{a['verb']} {a['path'][:70]} · {what}", status=status)

    # API1
    n_my = len(my)
    n_my_noauto = sum(1 for a in my if not a['auto'])
    api1 = 1 if n_my >= 5 else 0
    by_repo = dict(collections.Counter(a['repo'] for a in my))
    V['backend.api.API1'] = _item('API 기본(내 실질 API 5개 이상)', 1, api1, 'value_rule', ratio=dict(count=n_my, need=5, near_edge=abs(n_my - 5) <= 1), by_repo=by_repo,
                                  definition='「문서」 내 실질 API 5개 이상(헬스 체크·자동 생성 API 제외). 내 API = 「제안」[B-43] 라우트 정의 + 핸들러 본문 줄(빈 줄·주석 뺌) 중 내 줄 과반. '
                                             '레포 합계, (프레임워크, 메서드, 정규화한 경로, 핸들러 위치)로 한 번. Django ModelViewSet·router가 만드는 동작도 센다(규칙 16)',
                                  inst=[inst(a, 'counted', 'mine') for a in my] + [inst(a, 'excluded', 'not mine') for a in sub if a['mine'] is False][:100] +
                                       [inst(a, 'excluded', 'health/docs') for a in apis if a['health']][:20],
                                  notes=f'blame 없는 API {len(unknown_mine)}개는 세지 않음(못 뽑힌 것)')
    data['definition_choices'].append(dict(item='B-43 내 API 기준', choice='A 과반',
                                           why='라우트 한 줄만 쓴 사람(B)이나 한 줄 고친 사람(C)보다 핸들러를 실제로 쓴 사람을 고른다. 팀 레포에서 B·C는 남의 API를 내 것으로 크게 늘린다',
                                           alternatives={'A 과반(정의+본문)': n_my, 'B 라우트 정의 줄': sum(1 for a in sub if a['mine_def']), 'C 한 줄 이상': sum(1 for a in sub if a['mine_any'])}))
    data['definition_choices'].append(dict(item='B-49 자동 생성 API(Django ModelViewSet·router)', choice='센다',
                                           why='규칙 16 스택 공정성: 같은 CRUD를 Spring은 손으로, DRF는 선언으로 만든다. admin·actuator·문서 경로는 뺀다',
                                           alternatives={'센다': n_my, '뺀다': n_my_noauto}))

    # API2 주소 규칙
    a2 = [(a, api2_judge(a)) for a in my]
    den2 = [x for x in a2 if x[1][0] != 'auth']
    num2 = sum(1 for a, j in den2 if j[0] == 'pass')
    p2 = half_pass(num2, len(den2))
    num2s = sum(1 for a, j in a2 if j[1] == 'pass')
    p2s = half_pass(num2s, len(a2))
    num2b = sum(1 for a, j in a2 if j[0] == 'pass')
    V['backend.api.API2'] = _item('주소 규칙(절반 이상)', 1, (1 if p2 else 0) if p2 is not None else 0, 'value_rule',
                                  ratio=dict(num=num2, den=len(den2), near_edge=len(den2) > 2 and abs(num2 * 2 - len(den2)) <= 2), by_repo=_by_repo_ratio(den2, lambda j: j[0] == 'pass'),
                                  definition='「문서」 주소는 명사, 하는 일은 HTTP 메서드로 구분(절반 이상). 규칙: 경로 조각(낱말 처음·끝)에 CRUD 동사(create·update·delete·get·add·modify·edit·save·write 등)가 있으면 위반. '
                                             '「Claude 정의」 인증 동작 주소(login·logout·signup·token·oauth·me 등)는 분모에서 뺀다. list·detail·search는 명사로 본다',
                                  inst=[inst(a, 'counted' if j[0] == 'pass' else ('excluded' if j[0] == 'auth' else 'counted'), f"{j[0]} {','.join(j[2])}") for a, j in a2])
    data['definition_choices'].append(dict(item='B-49 API2 인증 동작·검색 주소', choice='인증 동작 주소는 분모에서 빼고, list·detail·search는 명사로 봄',
                                           why='로그인·토큰 재발급은 자원 CRUD가 아니라 관례상 동작 주소를 쓴다. CRUD 동사(메서드와 겹치는 뜻)만 위반으로 본다',
                                           alternatives={'인증 뺌·명사 허용(고름)': f'{num2}/{len(den2)}',
                                                         '인증을 분모에 둠(통과 취급)': f'{num2b + sum(1 for a, j in a2 if j[0] == "auth")}/{len(a2)}',
                                                         '엄격(list·detail·view·form·search·new도 위반, 인증 포함)': f'{num2s}/{len(a2)}'}))

    # API3 입력 검사
    a3 = []
    for a in my:
        try:
            st, kinds = api3_judge(rc_of[a['repo']], a, models[a['repo']])
        except Exception as e:
            st, kinds = 'unclear', ['error:' + repr(e)[:40]]
        a3.append((a, st, kinds))
    den3 = [x for x in a3 if x[1] in ('pass', 'fail', 'unclear')]
    den3_alt = [x for x in a3 if x[1] in ('pass', 'fail', 'unclear', 'pathonly')]
    num3 = sum(1 for x in den3 if x[1] == 'pass')
    unc3 = [x for x in den3 if x[1] == 'unclear']
    for i, (a, st, kinds) in enumerate(sorted(unc3, key=lambda x: -(x[0]['hend'] - x[0]['hstart']))[:15]):
        a['t3'] = target('backend.api.API3', rc_of[a['repo']], 'API3.input_check', files=[dict(path=a['hfile'], start=max(1, a['hstart'] - 8), end=a['hend'] + 2)] +
                         ([dict(path=a['file'], start=max(1, a['line'] - 2), end=a['line'] + 3)] if a['file'] != a['hfile'] else []),
                         rule_result=dict(api=f"{a['verb']} {a['path']}", inputs=kinds, rule='unclear(손 검사·모델 검사 흔적)'), priority=3 + i // 5, group='API3', stop_rule='ratio_decided',
                         unit=a['id'])
    V['backend.api.API3'] = _ratio_item('입력 검사(절반 이상)', 1, [(a, st) for a, st, kinds in den3], 'API3',
                                        '「문서」 입력 받는 API(파일 업로드 포함)에 길이·범위·형식·크기 검사가 작동하게 연결(절반 이상). 분모 = 본문·쿼리·파일 입력을 받는 내 API. '
                                        '「Claude 정의」 경로 변수만 받는 API는 분모에서 뺀다. 타입 선언만은 검사가 아니다. Spring은 @Valid + DTO 제약 + validation 의존성, Nest는 class-validator + ValidationPipe, '
                                        'Express는 검사 미들웨어·스키마 parse, Django는 serializer·form + is_valid(generic view 포함), FastAPI는 Pydantic·Query 제약',
                                        [inst(a, 's5' if st == 'unclear' else ('counted' if st in ('pass', 'fail') else 'excluded'), f'{st} {kinds}') for a, st, kinds in a3])
    data['definition_choices'].append(dict(item='B-49 API3 경로 변수만 받는 API·타입 선언', choice='경로 변수만 받는 API는 분모에서 뺌, 타입 선언만은 검사 아님',
                                           why='id 경로 변수는 형 변환 말고 검사할 값이 없다. 반대로 본문 DTO에 타입만 있는 것은 길이·범위 검사가 없어 문서 기준에 못 미친다',
                                           alternatives={'경로 변수 API 뺌(고름)': f'{num3}/{len(den3)}(애매 {len(unc3)})',
                                                         '경로 변수 API 분모에 둠': f'{num3 + sum(1 for x in a3 if x[1] == "pass" and set(x[2]) <= {"path"})}/{len(den3_alt)}'}))

    # API4 필요한 값만 응답
    a4 = []
    for a in my:
        try:
            st = api4_judge(rc_of[a['repo']], a, models[a['repo']])
        except Exception as e:
            st = 'unclear'
        a4.append((a, st))
    den4 = [x for x in a4 if x[1] in ('pass', 'fail', 'unclear')]
    num4 = sum(1 for x in den4 if x[1] == 'pass')
    unc4 = [x for x in den4 if x[1] == 'unclear']
    for i, (a, st) in enumerate(unc4[:15]):
        a['t4'] = target('backend.api.API4', rc_of[a['repo']], 'API4.response_shape', files=[dict(path=a['hfile'], start=max(1, a['hstart'] - 6), end=a['hend'] + 2)],
                         rule_result=dict(api=f"{a['verb']} {a['path']}", rule='unclear(반환 모양을 규칙으로 못 정함)'), priority=3 + i // 5, group='API4', stop_rule='ratio_decided', unit=a['id'])
    V['backend.api.API4'] = _ratio_item('필요한 값만 응답(절반 이상)', 1, den4, 'API4',
                                        '「문서」 DB 모델을 그대로 반환하지 않고 응답 모양을 따로 정함(절반 이상). 「Claude 정의」[B-49] 분모 = DB 데이터를 돌려주는 내 REST API(메시지·void·화면 렌더 API 뺌). '
                                        '반환 타입·serializer fields·response_model·res.json 인자로 판정',
                                        [inst(a, 's5' if st == 'unclear' else ('counted' if st in ('pass', 'fail') else 'excluded'), st) for a, st in a4])
    data['definition_choices'].append(dict(item='B-49 API4 분모', choice='DB 데이터를 돌려주는 API만',
                                           why='메시지·void를 돌려주는 API는 DB 모델을 내보낼 일이 없어 통과로 세면 비율이 부풀고, 실패로 세면 억울하다',
                                           alternatives={'DB 데이터 API만(고름)': f'{num4}/{len(den4)}', '실질 REST API 전부(nodata는 통과)': f'{num4 + sum(1 for x in a4 if x[1] == "nodata")}/{len(den4) + sum(1 for x in a4 if x[1] == "nodata")}'}))

    # API5 오류 응답 통일(레포마다, 가장 좋은 것)
    a5 = {}
    for rc in rcs:
        try:
            a5[rc.key] = api5_repo(rc)
        except Exception as e:
            a5[rc.key] = dict(ok=False, why='분석 실패 ' + repr(e)[:60], ev=None, trace=None)
    ok5 = [k for k, v in a5.items() if v['ok']]
    V['backend.api.API5'] = _item('오류 응답 통일', 1, 1 if ok5 else 0, 'value_rule', by_repo={k: (1 if v['ok'] else 0) for k, v in a5.items()},
                                  ev_=[v['ev'] for v in a5.values() if v['ok'] and v['ev']],
                                  definition='「문서」 전역 예외 처리로 같은 모양 + 알맞은 상태 코드 2종 이상. 한 레포 안에서 채움(「제안」[B-57]). 처리기는 내 줄(과반 또는 선언 줄). '
                                             'Spring @RestControllerAdvice(+오류 코드 enum의 상태), Nest 전역 ExceptionFilter, Express 에러 미들웨어, FastAPI exception_handler, DRF EXCEPTION_HANDLER',
                                  inst=[dict(repo=k, path=(v['trace'] or (None, None))[0], line=(v['trace'] or (None, None))[1], what=v['why'], status='counted' if v['ok'] else 'excluded') for k, v in a5.items()])

    # API6 목록 나눠 보내기
    a6 = []
    for a in my:
        rc = rc_of[a['repo']]
        sp = _settings_page(rc)
        try:
            is_list, st = api6_judge(rc, a, models[a['repo']], sp)
        except Exception:
            is_list, st = False, None
        if is_list:
            a6.append((a, st))
    num6 = sum(1 for a, st in a6 if st == 'pass')
    if not a6:
        V['backend.api.API6'] = _item('목록 나눠 보내기(절반 이상)', 1, None, 'not_applicable', definition='「문서」 목록 API에 페이지네이션(절반 이상). 목록 API 0개면 해당 없음(규칙 4)', notes='목록 API 0개')
    else:
        V['backend.api.API6'] = _ratio_item('목록 나눠 보내기(절반 이상)', 1, a6, 'API6',
                                            '「문서」 목록 API에 페이지네이션(절반 이상). 목록 API = 여러 건을 돌려주는 내 GET API(List·Page 반환, 전체 조회). 페이지 = Pageable·page/size/limit/offset/cursor·skip/take·pagination_class',
                                            [inst(a, 'counted', st) for a, st in a6])

    # API7 외부 API
    s7, s7_five = [], []
    for rc in rcs:
        try:
            s7 += [dict(x, repo=rc.key) for x in api7_sites(rc)]
        except Exception as e:
            data['stats'].setdefault('errors', []).append(f'{rc.key}: api7 {repr(e)[:100]}')
    s7_five = [x for x in s7 if x['kind'] != '그 밖']
    if not s7:
        V['backend.api.API7'] = _item('외부 API(절반 이상)', 1, None, 'not_applicable', definition='「문서」 외부 서비스 호출 0개면 해당 없음(만점 8)', notes='외부 호출 지점 0개')
    else:
        den7 = [(x, x['state']) for x in s7]
        num7 = sum(1 for x in s7 if x['state'] == 'pass')
        for i, x in enumerate([x for x in s7 if x['state'] == 'unclear'][:10]):
            x['t'] = target('backend.api.API7', rc_of[x['repo']], 'API7.external_call', files=[dict(path=x['path'], start=max(1, x['line'] - 25), end=x['line'] + 25)],
                            rule_result=dict(kind=x['kind'], timeout=x['timeout'], fail=x['fail']), priority=4 + i // 5, group='API7', stop_rule='ratio_decided')
        V['backend.api.API7'] = _ratio_item('외부 API(절반 이상)', 1, den7, 'API7',
                                            '「문서」 외부 서비스(결제·메일·지도·AI·파일 저장소)를 부르는 곳에 직접 설정한 타임아웃 + 실패 처리(오류 응답·재시도). 분모 = 내 호출 지점(우리 서버 호출 뺌). '
                                            '「Claude 정의」[B-49] 다섯 종류 밖 외부 서비스(공공 API 등)도 넣는다',
                                            [dict(repo=x['repo'], path=x['path'], line=x['line'], what=f"{x['kind']} timeout={x['timeout']} fail={x['fail']}", status='s5' if x['state'] == 'unclear' else 'counted') for x in s7])
    data['definition_choices'].append(dict(item='B-49 API7 다섯 종류 밖 외부 서비스', choice='넣는다',
                                           why='문서 괄호는 예시로 읽었다. 공공·날씨 API도 타임아웃·실패 처리가 똑같이 필요하다',
                                           alternatives={'모든 외부 서비스(고름)': f"{sum(1 for x in s7 if x['state'] == 'pass')}/{len(s7)}",
                                                         '다섯 종류만': f"{sum(1 for x in s7_five if x['state'] == 'pass')}/{len(s7_five)}"}))

    # API8 캐시(가점형)
    a8 = {}
    for rc in rcs:
        try:
            a8[rc.key] = api8_repo(rc)
        except Exception as e:
            a8[rc.key] = dict(state='unused', why='분석 실패 ' + repr(e)[:60], ev=None, trace=None)
    st8 = 'pass' if any(v['state'] == 'pass' for v in a8.values()) else ('unclear' if any(v['state'] == 'unclear' for v in a8.values()) else
                                                                        ('wrong' if any(v['state'] == 'wrong' for v in a8.values()) else 'unused'))
    for k, v in a8.items():
        if v['state'] == 'unclear' and v['trace']:
            v['t'] = target('backend.api.API8', rc_of[k], 'API8.cache', files=[dict(path=v['trace'][0], start=max(1, v['trace'][1] - 30), end=v['trace'][1] + 40)],
                            rule_result=dict(why=v['why']), priority=6, group='API8', stop_rule='first_yes')
    V['backend.api.API8'] = _item('캐시(가점형)', 1, 1 if st8 == 'pass' else 0, 'value_rule' if st8 in ('pass', 'wrong') else ('zero_unused' if st8 == 'unused' else None),
                                  by_repo={k: v['state'] for k, v in a8.items()}, ev_=[v['ev'] for v in a8.values() if v['ev']],
                                  definition='「문서」 만료 시간 + 우리 DB 데이터면 바뀔 때 삭제(외부 응답은 만료만) + 작동 연결. 가점형: 제대로 하면 점수·만점 +1, 안 쓰거나 틀리면 계산에서 뺌(규칙 5). '
                                             '「제안」 Redis를 토큰·인증 코드 저장에만 쓰면 캐시 아님',
                                  inst=[dict(repo=k, path=(v['trace'] or (None, None))[0], line=(v['trace'] or (None, None))[1], what=v['why'], status='s5' if v['state'] == 'unclear' else 'counted') for k, v in a8.items()],
                                  notes=f'상태 {st8}')
    V['backend.api.API8']['bonus_state'] = st8

    # API9 테스트
    tix = {}
    for rc in rcs:
        try:
            tix[rc.key] = test_index(rc)
        except Exception as e:
            tix[rc.key] = ([], collections.Counter(), set())
    a9 = [(a, 'pass' if api9_cover(rc_of[a['repo']], a, tix[a['repo']]) else 'fail') for a in my]
    num9 = sum(1 for a, s in a9 if s == 'pass')
    p9 = half_pass(num9, len(a9))
    V['backend.api.API9'] = _item('테스트(절반 이상)', 2, 2 if p9 else 0, 'value_rule', ratio=dict(num=num9, den=len(a9), near_edge=len(a9) > 2 and abs(num9 * 2 - len(a9)) <= 2),
                                  by_repo=_by_repo_ratio(a9, lambda s: s == 'pass'),
                                  definition='「문서」 실질 API의 절반 이상을 내 테스트(API 테스트 또는 그 API가 부르는 서비스 테스트)가 다룸. 정적으로 봄: 내 테스트 줄의 경로 문자열 + HTTP 호출 + 단언, '
                                             'Django reverse(url 이름), 서비스 테스트(핸들러가 부르는 클래스·메서드 이름 + 단언). 401·403만 단언하는 테스트는 뺌(규칙 7). 자동 생성(contextLoads) 뺌',
                                  inst=[inst(a, 'counted', s) for a, s in a9], notes='2점 항목: 해당 없음 없음, 부분 점수 없음(「미정」[B-49])')
    if not a9:
        V['backend.api.API9']['state'] = 'value_rule'
        V['backend.api.API9']['value'] = 0

    # API-C1 상한
    c1 = collections.defaultdict(list)
    for a in my:
        try:
            r_ = apic1(rc_of[a['repo']], a, models[a['repo']])
        except Exception:
            r_ = None
        if r_:
            c1[a['repo']].append((a, r_))
    for k, lst in c1.items():
        for i, (a, r_) in enumerate([x for x in lst if x[1] == 'unclear'][:3]):
            a['tc1'] = target('backend.api.API-C1', rc_of[k], 'API-C1.password_response', files=[dict(path=a['hfile'], start=max(1, a['hstart'] - 5), end=a['hend'] + 2)],
                              rule_result=dict(api=f"{a['verb']} {a['path']}", rule='unclear'), priority=2, group='API-C1.' + k, stop_rule='first_yes')
    V['backend.api.API-C1'] = _item('상한: 비밀번호가 응답에 나감', None, None, 'value_rule', role='cap',
                                    by_repo={k: ('certain' if any(r_ == 'certain' for _, r_ in v) else 'unclear') for k, v in c1.items()},
                                    definition='「문서」 비밀번호(해시 포함)가 응답에 나감 → 최대 2. 「제안」 확실할 때만 건다(엔티티·응답 DTO에 비밀번호 칸 + 직렬화 제외 없음, serializer fields·__all__, response_model)',
                                    inst=[inst(a, 'counted' if r_ == 'certain' else 's5', r_) for v in c1.values() for a, r_ in v])

    # ---------------- 로그
    l1 = {rc.key: log1_repo(rc) for rc in rcs}
    used1 = [k for k, v in l1.items() if v['used']]
    tot_calls = sum(v['my_calls'] for v in l1.values())
    tot_prints = sum(v['my_prints'] for v in l1.values())
    V['backend.log.LOG1'] = _item('로그 기본(로깅 라이브러리)', 1, 1 if used1 else 0, 'value_rule' if used1 else ('zero_unused' if not any(v['trace'] for v in l1.values()) else 'value_rule'),
                                  by_repo={k: dict(used=v['used'], my_logger_calls=v['my_calls'], my_print_calls=v['my_prints']) for k, v in l1.items()},
                                  ev_=[v['ev'] for v in l1.values() if v['ev']],
                                  definition='「문서」 print·console.log 대신 로깅 라이브러리 사용. 레포 단위(규칙 9, 있는지만): 백엔드 파일에 로거 생성(LoggerFactory·@Slf4j·winston·pino·Nest Logger·logging.getLogger 등) + 로거 호출',
                                  notes=f'내 로거 호출 {tot_calls} · 내 print/console 호출 {tot_prints}')
    alt1b = 1 if (used1 and tot_prints == 0) else 0
    alt1c = 1 if (used1 and tot_calls >= tot_prints) else 0
    data['definition_choices'].append(dict(item='B-50 LOG1 print·console.log가 섞임', choice='섞여도 인정(로거가 있고 부름)',
                                           why='문서가 레포 단위·있는지만으로 정했다(규칙 9). 섞임 정도는 내 로거·print 호출 수로 따로 보인다',
                                           alternatives={'섞여도 인정(고름)': 1 if used1 else 0, '내 print 0개일 때만': alt1b, '내 로거 호출 ≥ 내 print 호출': alt1c}))

    l2 = {}
    for rc in rcs:
        cs = catches(rc)
        g_ok, g_ev, g_where = global_500_log(rc)
        empty_main = [c for c in cs if c['empty']]
        empty_len = [c for c in cs if c['empty'] and not c['comment_only']]
        broad_bad = [c for c in cs if c['broad'] and not c['keep'] and not c['empty']]
        ok = not empty_main and not broad_bad and g_ok
        l2[rc.key] = dict(ok=ok, ok_lenient=(not empty_len and not broad_bad and g_ok), catches=len(cs), empty=len(empty_main), comment_only=len(empty_main) - len(empty_len),
                          broad_bad=len(broad_bad), global_ok=g_ok, ev=g_ev, where=g_where, first_bad=(empty_main + broad_bad)[:5])
    ok2 = [k for k, v in l2.items() if v['ok']]
    V['backend.log.LOG2'] = _item('예외 로그', 1, 1 if ok2 else 0, 'value_rule', by_repo={k: dict(ok=v['ok'], catches=v['catches'], empty=v['empty'], broad_no_cause=v['broad_bad'], global_500_log=v['global_ok'])
                                                                                    for k, v in l2.items()},
                                  ev_=[v['ev'] for v in l2.values() if v['ok'] and v['ev']],
                                  definition='「문서」 빈 catch 0개 + 특정 예외만 골라 처리하고 나머지는 원인 보존 재던짐 또는 스택 로그 + 전역 처리기가 500을 스택과 함께 error 로그. 내 catch만, 한 레포 안(「제안」[B-57]). '
                                             '「Claude 정의」[B-50] 주석만 있는 catch는 빈 catch. JS catch는 모두 넓은 예외로 본다',
                                  inst=[dict(repo=k, path=c['path'], line=c['line'], what=('empty' if c['empty'] else 'broad-no-cause'), status='counted') for k, v in l2.items() for c in v['first_bad']] +
                                       [dict(repo=k, path=(v['where'] or (None, None))[0], line=(v['where'] or (None, None))[1], what=f"global500={v['global_ok']}", status='counted') for k, v in l2.items()])
    data['definition_choices'].append(dict(item='B-50 LOG2 주석만 있는 catch', choice='빈 catch로 봄',
                                           why='주석은 예외를 처리하지도 원인을 남기지도 않는다. 이 항목은 예외가 조용히 사라지는 것을 막는 것이다',
                                           alternatives={'빈 catch로 봄(고름)': 1 if ok2 else 0, '빈 catch 아님': 1 if any(v['ok_lenient'] for v in l2.values()) else 0,
                                                         '주석만 catch 수': sum(v['comment_only'] for v in l2.values())}))

    l3 = {rc.key: log3_repo(rc) for rc in rcs}
    own3 = {k: v[0] for k, v in l3.items() if v[0]}
    lib3 = {k: v[1] for k, v in l3.items() if v[1]}
    ok3 = bool(own3 or lib3)
    V['backend.log.LOG3'] = _item('요청 로그', 1, 1 if ok3 else 0, 'value_rule' if ok3 else ('zero_unused' if not any(v[2] for v in l3.values()) else 'value_rule'),
                                  by_repo={k: dict(own=len(v[0]), library=len(v[1])) for k, v in l3.items()},
                                  ev_=[ev(rc_of[k], path=p, line=ln, rule='backend.log.LOG3.own-mw' + RULE_V) for k, v in own3.items() for p, ln in v[:1]] +
                                      [ev(rc_of[k], path=p, line=ln, rule='backend.log.LOG3.lib-mw' + RULE_V) for k, v in lib3.items() for p, ln in v[:1]],
                                  definition='「문서」 요청마다 경로·상태 코드·처리 시간을 미들웨어·필터 한 곳에서 기록. 내 코드: 필터·인터셉터·미들웨어 한 파일에 시각 재기 + 경로 + 상태 + 로그 호출(내 줄). '
                                             '「Claude 정의」[B-50] 라이브러리 미들웨어(morgan dev·tiny 등 처리 시간이 든 형식, pino-http)와 켠 access 로그(처리 시간 패턴)도 인정',
                                  inst=[dict(repo=k, path=p, line=ln, what='own', status='counted') for k, v in own3.items() for p, ln in v[:3]] +
                                       [dict(repo=k, path=p, line=ln, what='library', status='counted') for k, v in lib3.items() for p, ln in v[:3]])
    data['definition_choices'].append(dict(item='B-50 LOG3 라이브러리 미들웨어·기본 access 로그', choice='처리 시간이 찍히는 형식으로 켰으면 인정',
                                           why='문서는 직접 만들라고 하지 않았고 경로·상태·시간 셋이 한 곳에서 찍히면 목적을 채운다. morgan combined처럼 시간이 없는 형식은 뺀다',
                                           alternatives={'라이브러리 인정(고름)': 1 if ok3 else 0, '직접 만든 것만': 1 if own3 else 0}))

    l4 = {rc.key: log4_repo(rc) for rc in rcs}
    ok4 = [k for k, (lv, kp, hits) in l4.items() if lv and kp]
    V['backend.log.LOG4'] = _item('로그 설정', 1, 1 if ok4 else 0, 'value_rule', by_repo={k: dict(level=len(lv), keep=len(kp), seen=len(h)) for k, (lv, kp, h) in l4.items()},
                                  ev_=[ev(rc_of[k], path=x['path'], line=x['line'], rule='backend.log.LOG4.cfg' + RULE_V) for k in ok4 for x in (l4[k][0][:1] + l4[k][1][:1])],
                                  definition='「문서」 운영 로그 레벨 + 보관(파일·보관 기간, 또는 stdout + 로그 드라이버). 한 레포 안에서 레벨 설정 + 보관 설정(롤링·maxHistory·backupCount·compose logging driver 등). '
                                             '설정 파일은 내 줄 과반(규칙 9), dev·local·test 이름 파일은 운영 설정 아님',
                                  inst=[dict(repo=k, path=x['path'], line=x['line'], what=f"level={x['level']} keep={x['keep']} mine={x['mine']} prod={x['prod']}", status='counted') for k, (lv, kp, h) in l4.items() for x in h[:6]])
    for k, (lv, kp, h) in l4.items():
        if not (lv and kp) and any(x['keep'] or x['level'] for x in h):
            x = next(x for x in h if x['keep'] or x['level'])
            target('backend.log.LOG4', rc_of[k], 'LOG4.log_config', files=[dict(path=x['path'], start=1, end=200)], rule_result=dict(level=bool(lv), keep=bool(kp)), priority=7,
                   group='LOG4', stop_rule='first_yes')
            break

    l5 = {rc.key: log5_repo(rc) for rc in rcs}
    ok5_ = [k for k, (s, f, tr) in l5.items() if s and any(x[2] for x in f)]
    V['backend.log.LOG5'] = _item('요청 추적 ID', 2, 2 if ok5_ else 0, 'value_rule' if (ok5_ or any(s or f for s, f, tr in l5.values())) else 'zero_unused',
                                  by_repo={k: dict(set=len(s), format=len(f)) for k, (s, f, tr) in l5.items()},
                                  ev_=[ev(rc_of[k], path=l5[k][0][0][0], line=l5[k][0][0][1], rule='backend.log.LOG5.set' + RULE_V) for k in ok5_],
                                  definition='「문서」 요청마다 ID를 붙여 그 요청의 모든 로그에 남김. 요청 진입 코드에서 ID 넣기(MDC.put·AsyncLocalStorage·ContextVar set 등, 내 줄) + 로그 형식에 ID(%X{..}·포매터, 내 줄 또는 공용 설정 과반)',
                                  inst=[dict(repo=k, path=p, line=ln, what='set', status='counted') for k, (s, f, tr) in l5.items() for p, ln, _ in s[:3]] +
                                       [dict(repo=k, path=p, line=ln, what=f'format mine={m_}', status='counted') for k, (s, f, tr) in l5.items() for p, ln, m_ in f[:3]])
    for k, (s, f, tr) in l5.items():
        if (s or f) and k not in ok5_:
            x = (s or f)[0]
            target('backend.log.LOG5', rc_of[k], 'LOG5.trace_id', files=[dict(path=x[0], start=max(1, x[1] - 30), end=x[1] + 40)], rule_result=dict(set=len(s), format=len(f)), priority=6,
                   group='LOG5', stop_rule='first_yes')
            break

    # LOG6
    cands = []
    loose_n = 0
    for rc in rcs:
        cs = log6_candidates(rc.repo)
        loose_n += sum(1 for c in log6_candidates(rc.repo, loose=True) if c['test_in_commit'] or c['test_in_pr'])
        for c in cs:
            c['repo'] = rc.key
        cands += cs
    send6 = [c for c in cands if c['test_in_commit'] or c['test_in_pr']]
    send6.sort(key=lambda c: (not c['cause_word'], not c['pr_body'], c['date']))
    for i, c in enumerate(send6[:25]):
        repo = rc_of[c['repo']].repo
        extra = []
        if c['pr'] and not c['test_in_commit']:       # 같은 PR의 테스트 커밋(분석 브랜치 안에 있는 것만, 「제안」[B-20])
            extra = [x['sha'] for x in repo.commits if x.get('pr') == c['pr'] and x['sha'] != c['sha'] and any(L.TEST.search(f['path']) for f in x['files'])][:2]
        c['t'] = target('backend.log.LOG6', rc_of[c['repo']], 'LOG6.cause_record', commits=[c['sha']] + extra, files=[],
                        text=(f"같은 PR #{c['pr']}. " if c['pr'] else '') + (f"같은 커밋에서 바꾼 문서: {', '.join(c['docs'])}. " if c['docs'] else '') +
                             f"테스트 변경: {', '.join(c['tests'][:4])}",
                        rule_result=dict(test_in_commit=c['test_in_commit'], test_in_pr=c['test_in_pr'], cause_word=c['cause_word'], pr=c['pr'], pr_body=c['pr_body'], tests=c['tests'][:4]),
                        priority=(1 if c['cause_word'] else 2) + (0 if c['pr_body'] else 1), group='LOG6', stop_rule='first_yes')
    V['backend.log.LOG6'] = _item('원인 찾은 기록 [AI 확인]', 2, 0 if not send6 else None, 'value_rule' if not send6 else None,
                                  by_repo=dict(collections.Counter(c['repo'] for c in send6)),
                                  definition='「문서」 버그 수정 커밋에 원인 + 같은 커밋·PR에 회귀 테스트. 「사용자 결정(2026-11-25)」 원인이 커밋 메시지·PR 설명·같은 커밋에서 바꾼 문서에 있으면 인정, 그 버그의 원인이어야 함(LLM 확인). '
                                             '후보 = 내 커밋 중 FIX_STRICT 정규식(옛 스파이크) + 같은 커밋 또는 같은 PR에 테스트 파일 변경. 테스트 변경이 없으면 회귀 테스트 아니오로 확정(LLM 안 부름)',
                                  inst=[dict(repo=c['repo'], path=None, line=None, what=f"{c['sha'][:8]} test_commit={c['test_in_commit']} test_pr={c['test_in_pr']} cause_word={c['cause_word']}",
                                             status='s5' if (c['test_in_commit'] or c['test_in_pr']) else 'excluded') for c in cands],
                                  notes=f"수정 낱말 커밋 {len(cands)} · 테스트 변경 있음 {len(send6)}(S5, 1건 yes면 2점)")
    V['backend.log.LOG6']['ai_check'] = True
    data['definition_choices'].append(dict(item='LOG6 후보 정규식', choice='FIX_STRICT(옛 스파이크 그대로)',
                                           why="'수정'까지 넣으면 기능 수정·리팩터링 커밋이 크게 늘어 LLM 비용만 는다(스파이크: 정규식 확정 57개 중 25개가 버그 수정 아님)",
                                           alternatives={'FIX_STRICT(고름)': len(send6), "FIX_STRICT + '수정'": loose_n}))

    # LOG-C1
    lc = {}
    for rc in rcs:
        cert, unc = logc1_repo(rc)
        lc[rc.key] = (cert, unc)
        for i, (p, ln) in enumerate(unc[:2]):
            target('backend.log.LOG-C1', rc, 'LOG-C1.secret_log', files=[dict(path=p, start=max(1, ln - 15), end=ln + 10)],
                   rule_result=dict(rule='요청 본문 전체를 로그(인증·회원 파일)'), priority=5, group='LOG-C1.' + rc.key, stop_rule='first_yes')
    V['backend.log.LOG-C1'] = _item('상한: 비밀번호·토큰을 로그에 남김', None, None, 'value_rule', role='cap', by_repo={k: dict(certain=len(c), unclear=len(u)) for k, (c, u) in lc.items()},
                                    definition='「문서」 비밀번호·토큰을 로그에 남김 → 최대 2. 「제안」 확실할 때만: 내 로그·print 호출 인자에 password·token·secret·Authorization 값(변수·getter·req.body.password). '
                                               '요청 본문 전체 로그는 애매(S5)',
                                    inst=[dict(repo=k, path=p, line=ln, what='certain', status='counted') for k, (c, u) in lc.items() for p, ln in c[:5]] +
                                         [dict(repo=k, path=p, line=ln, what='body', status='s5') for k, (c, u) in lc.items() for p, ln in u[:5]])

    # ---------------- 흔적 없는 0(no_trace) 표본: 변수마다 내 백엔드 줄이 많은 레포 3개
    big = sorted(rcs, key=lambda rc: -(rc.g.get('my_backend_lines') or 0))[:3]
    for vid, ok_, tmpl in (('backend.log.LOG3', ok3, 'LOG3.request_log'), ('backend.log.LOG5', bool(ok5_), 'LOG5.trace_id'), ('backend.api.API5', bool(ok5), 'GEN.no_trace')):
        if ok_ or V[vid]['state'] != 'zero_unused' and vid != 'backend.api.API5':
            continue
        for rc in big:
            if vid == 'backend.api.API5' and a5.get(rc.key, {}).get('trace'):
                continue
            fl = sorted(rc.bfiles, key=lambda p: -(len(rc.own(p) or ())))[:2]
            target(vid, rc, tmpl, files=[dict(path=p, start=1, end=120) for p in fl], rule_result=dict(item=vid, rule='흔적 없음(0 안 씀)'), trace='no_trace', priority=9)

    # ---------------- 부가 기술 영역
    _ext(person, data, rcs, target)

    # ---------------- 변수 점수
    data['stats']['seconds'] = round(time.time() - t0, 1)
    data['stats']['s5_targets'] = dict(collections.Counter(t['var'] for t in T))
    compute(data, {})
    return data


def _settings_page(rc):
    if not hasattr(rc, '_sp'):
        rc._sp = False
        for p in rc.configs():
            if p.endswith('.py') and re.search(r'DEFAULT_PAGINATION_CLASS', rc.text(p) or ''):
                rc._sp = True
    return rc._sp


def _by_repo_ratio(lst, okf):
    d = collections.defaultdict(lambda: [0, 0])
    for a, j in lst:
        d[a['repo']][1] += 1
        if okf(j):
            d[a['repo']][0] += 1
    return {k: f'{v[0]}/{v[1]}' for k, v in d.items()}


def _ratio_item(name, points, units, gid, definition, inst):
    """비율 항목: units = [(api 또는 지점, 'pass'|'fail'|'unclear')]. 값은 compute()가 S5 답까지 넣어 정한다."""
    tids = []
    for a, st in units:
        tid = a.get('t3') if gid == 'API3' else a.get('t4') if gid == 'API4' else a.get('t') if gid == 'API7' else None
        tids.append(dict(unit=a.get('id') or f"{a.get('path')}:{a.get('line')}", repo=a.get('repo'), rule=st, target=tid))
    d = _item(name, points, None, None, ratio=dict(num=sum(1 for _, s in units if s == 'pass'), den=len(units), unclear=sum(1 for _, s in units if s == 'unclear')),
              definition=definition, inst=inst, by_repo=_by_repo_ratio(units, lambda s: s == 'pass'))
    d['_units'] = tids
    return d


def _units_for_finalize(V):
    return {vid: v.get('_units') for vid, v in V.items() if v.get('_units')}


def _ext(person, data, rcs, target):
    V = data['variables']
    main = {k: [] for k in EXT_NAME}
    lvl = {}
    sse_all, dflt_all = [], []
    for rc in rcs:
        res, sse, _ = ext_scan(rc.repo, rc, rc.bfiles + [p for p in rc.configs() if not p.endswith('.py') or 'settings' in p], True)
        anyauthor, _, _ = ext_scan(rc.repo, rc, rc.bfiles + rc.configs(), False)
        lvl[rc.key] = dict(main={k: len(v) for k, v in res.items()}, repo_level={k: len(v) for k, v in anyauthor.items()})
        for k, v in res.items():
            main[k] += [(rc, p, ln) for p, ln in v]
        sse_all += [(rc, p, ln) for p, ln in sse]
        dflt_all += [(rc.key, x[0]) for x in ext_default_on(rc)]
        # 흔적(의존성)이 있는데 규칙이 못 찾은 영역 → S5
        deps = ' '.join(t or '' for t in (rc.ctx.get('build_texts') or {}).values())
        for k in EXT_NAME:
            if not res[k] and EXT_DEP[k].search(deps) and not (k == 'EXT3' and re.search(r'(?i)fastapi', deps) and not re.search(r'(?i)swagger|spectacular|yasg|springdoc', deps)):
                cand = sorted([p for p in rc.bfiles if re.search({'EXT1': r'(?i)s3|upload|storage|file|image|aws', 'EXT2': r'(?i)socket|chat|ws|realtime|stomp|message',
                                                                   'EXT3': r'(?i)swagger|openapi|doc|config', 'EXT4': r'(?i)oauth|kakao|google|naver|social|login|auth'}[k], p)],
                              key=lambda p: -len(rc.own(p) or ()))[:3]
                if cand:
                    target('backend.extras.' + k, rc, 'EXT.area', files=[dict(path=p, start=1, end=150) for p in cand],
                           rule_result=dict(area=EXT_NAME[k], dependency=True, rule_hit=False), priority=8, group='EXT.' + k, stop_rule='first_yes')
    alt_all = _ext_other_repos(person, {rc.key for rc in rcs})
    # 흔적 없는 0: 영역마다 내 백엔드 줄이 많은 레포 3개를 no_trace 표본 후보로
    big = sorted(rcs, key=lambda rc: -(rc.g.get('my_backend_lines') or 0))[:3]
    for k in EXT_NAME:
        if main[k] or any(t['var'] == 'backend.extras.' + k for t in data['s5_targets']):
            continue
        for rc in big:
            fl = sorted(rc.bfiles, key=lambda p: -(len(rc.own(p) or ())))[:2]
            target('backend.extras.' + k, rc, 'EXT.area', files=[dict(path=p, start=1, end=120) for p in fl],
                   rule_result=dict(area=EXT_NAME[k], rule='흔적 없음(0 안 씀)'), trace='no_trace', priority=9)
    n_main = sum(1 for k in EXT_NAME if main[k])
    n_all = sum(1 for k in EXT_NAME if main[k] or alt_all[k])
    n_repo = sum(1 for k in EXT_NAME if any(x['repo_level'][k] for x in lvl.values()))
    n_sse = sum(1 for k in EXT_NAME if main[k] or (k == 'EXT2' and sse_all))
    for k, nm in EXT_NAME.items():
        hits = main[k]
        V['backend.extras.' + k] = _item(nm, None, bool(hits), 'value_rule' if hits else 'zero_unused', unit='T/F', role='tf',
                                         by_repo={rc.key: sum(1 for x in hits if x[0] is rc) for rc in rcs},
                                         ev_=[ev(rc, path=p, line=ln, rule=f'backend.extras.{k}.call-or-config' + RULE_V) for rc, p, ln in hits[:5]],
                                         inst=[dict(repo=rc.key, path=p, line=ln, what='hit', status='counted') for rc, p, ln in hits[:50]],
                                         definition='「문서」 썼다 = 내 코드에서 실제로 호출한 곳 1곳 이상 또는 설정 파일에 켜는 값(주석·끄는 값·예시 파일 X, 의존성·import만이면 X). '
                                                    '「제안」[B-53] 게이트 통과 레포의 백엔드 파일·설정, 내 줄만',
                                         notes=('SSE 흔적 있음(실시간에 안 셈)' if k == 'EXT2' and sse_all else '') + (' 기본값으로 켜짐: ' + ', '.join(sorted({x for _, x in dflt_all})) if k == 'EXT3' and dflt_all else ''))
    V['backend.extras'] = _item('부가 기술 영역 수(가점 재료)', None, n_main, 'value_rule' if n_main else 'zero_unused', unit='영역(0~4)', role='bonus_count',
                                by_repo={k: x['main'] for k, x in lvl.items()},
                                definition='「문서」 파일 저장소·실시간 통신·API 문서·소셜 로그인 중 쓴 영역 수(캐시는 API8에서). 단계 시작값·가점 방식은 「미정」[B-11]·[B-13]',
                                notes='단계·가점은 여기서 정하지 않음')
    data['definition_choices'].append(dict(item='B-53·B-42 부가 기술 영역 범위', choice='게이트 통과 레포의 백엔드 파일·설정, 내 줄만, SSE 제외, 기본값으로 켜짐 제외',
                                           why='클라이언트 SSE·화면 SDK 오탐을 막고(스파이크 교훈), 분석 범위 결정(본인 줄만)을 따른다',
                                           alternatives={'고름(백엔드·내 줄)': n_main, '모든 레포·내 줄': n_all, '백엔드·레포 단위(남의 줄 포함)': n_repo, 'SSE를 실시간에 넣음': n_sse}))


class _Lite:
    """게이트 밖 레포용 가벼운 문맥(한 번에 읽기)."""

    def __init__(self, repo, paths):
        self.repo, self.key = repo, repo.key
        self.t = G.batch_read(repo, paths, 400_000)
        self._mk, self._li = {}, {}

    def masks(self, p):
        if p not in self._mk:
            t = self.t.get(p)
            self._mk[p] = None if t is None else mask_py(t) if p.endswith('.py') else oc.strip_c(t) if re.search(r'\.(java|kt|js|jsx|ts|tsx|mjs|cjs)$', p) else mask_conf(p, t)
        return self._mk[p]

    def li(self, p):
        if p not in self._li:
            m = self.masks(p)
            self._li[p] = LineIdx(m[0]) if m else None
        return self._li[p]

    def mine(self, p, ln):
        s = self.repo.own_line_set(p)
        return bool(s) and ln in s


def _ext_other_repos(person, skip):
    """[B-53] 대안: 모든 레포(게이트 밖 포함)·내 줄. 게이트 밖 레포는 내 줄이 있는 코드·설정 파일만 읽는다."""
    alt = {k: 0 for k in EXT_NAME}
    for r in person.repos:
        if r.key in skip:
            continue
        paths = [f['path'] for f in r.files if f['kind'] in ('code', 'config') and (f.get('size') or 0) < 400_000 and not ENV_FILE.search(f['path']) and (f.get('my_lines') or 0) > 0]
        if not paths:
            continue
        lt = _Lite(r, paths)
        res, _, _ = ext_scan(r, lt, paths, True)
        for k, v in res.items():
            alt[k] += len(v)
    return alt


def _ext_all_repos(person, data, _):
    V = data['variables']
    alt_all = _ext_other_repos(person, set())
    for k, nm in EXT_NAME.items():
        V['backend.extras.' + k] = _item(nm, None, False, 'zero_unused', unit='T/F', role='tf', definition='게이트 통과 레포 없음', notes=f'모든 레포·내 줄로 보면 {alt_all[k]}곳')
    V['backend.extras'] = _item('부가 기술 영역 수(가점 재료)', None, 0, 'zero_unused', unit='영역(0~4)', role='bonus_count', definition='게이트 통과 레포 없음')
    data['definition_choices'].append(dict(item='B-53 부가 기술 영역 범위', choice='게이트 통과 레포만', why='백엔드 레포가 없으면 영역도 0',
                                           alternatives={'고름': 0, '모든 레포·내 줄': sum(1 for k in EXT_NAME if alt_all[k])}))


# ======================================================================== 점수 계산(S6 일부) · finalize
def _ratio_eval(units, answers):
    num = den = unc = wait = 0
    for u in units:
        st = u['rule']
        if st == 'unclear':
            a = answers.get(u['target']) if u['target'] else None
            if a and a.get('decision') in ('yes', 'no'):
                if a.get('value') in ('nodata', 'internal'):
                    continue
                st = 'pass' if a['decision'] == 'yes' else 'fail'
                u['llm'] = True
            elif a:
                unc += 1
                continue
            else:
                wait += 1
                continue
        if st in ('pass', 'fail'):
            den += 1
            num += st == 'pass'
    return num, den, unc, wait


def compute(data, answers):
    V = data['variables']
    if 'backend.api.API1' not in V:
        return data
    from_llm = collections.defaultdict(int)
    # 비율 항목 다시 계산
    for vid in ('backend.api.API3', 'backend.api.API4', 'backend.api.API6', 'backend.api.API7'):
        v = V.get(vid)
        if not v or v.get('state') == 'not_applicable' or not v.get('_units'):
            if v and v.get('state') is None and not v.get('_units'):
                v['value'], v['state'] = 0, 'value_rule'
            continue
        num, den, unc, wait = _ratio_eval(v['_units'], answers)
        llm = sum(1 for u in v['_units'] if u.get('llm'))
        v['ratio'].update(num=num, den=den, unknown_failed=unc, waiting=wait, from_llm=llm, near_edge=den > 2 and abs(num * 2 - den) <= 2)
        p = half_pass(num, den)
        if den == 0 and not wait:
            v['value'], v['state'] = (None, 'not_applicable') if vid in ('backend.api.API6', 'backend.api.API7') else (0, 'value_rule')
        else:
            v['value'] = 1 if p else 0
            v['state'] = 'value_llm' if llm else 'value_rule'
            if wait:
                v['s5'] = dict(status='대기', waiting=wait)
    # API8
    v8 = V['backend.api.API8']
    for t in data['s5_targets']:
        if t['var'] == 'backend.api.API8':
            a = answers.get(t['target_id'])
            if a and a.get('decision') == 'yes':
                v8.update(value=1, state='value_llm', bonus_state='pass')
            elif a and a.get('decision') == 'no' and v8.get('bonus_state') != 'pass':
                v8.update(value=0, state='value_llm', bonus_state='wrong')
            elif not a and v8.get('bonus_state') == 'unclear':
                v8['s5'] = dict(status='대기')
    # API-C1
    vc = V['backend.api.API-C1']
    cap_api = {}
    for k, s in vc['by_repo'].items():
        if s == 'certain':
            cap_api[k] = 'certain'
    for t in data['s5_targets']:
        if t['var'] == 'backend.api.API-C1':
            a = answers.get(t['target_id'])
            if a and a.get('decision') == 'yes':
                cap_api[t['repo']] = 'llm'
    # LOG6
    v6 = V['backend.log.LOG6']
    t6 = [t for t in data['s5_targets'] if t['var'] == 'backend.log.LOG6']
    if t6:
        ans6 = [answers.get(t['target_id']) for t in t6]
        if any(a and a.get('decision') == 'yes' for a in ans6):
            v6.update(value=2, state='value_llm')
        elif all(a and a.get('decision') == 'no' for a in ans6):
            v6.update(value=0, state='value_llm')
        elif all(a for a in ans6):
            v6.update(value=None, state='unknown_failed')
        else:
            v6.update(value=None, state=None, s5=dict(status='대기', waiting=sum(1 for a in ans6 if not a)))
    # LOG4·LOG5 S5
    for vid, pts in (('backend.log.LOG4', 1), ('backend.log.LOG5', 2), ('backend.log.LOG3', 1), ('backend.api.API5', 1)):
        for t in data['s5_targets']:
            if t['var'] == vid:
                a = answers.get(t['target_id'])
                if a and a.get('decision') == 'yes' and not V[vid]['value']:
                    V[vid].update(value=pts, state='value_llm')
    # LOG-C1
    vl = V['backend.log.LOG-C1']
    cap_log = {k: 'certain' for k, x in vl['by_repo'].items() if x['certain']}
    for t in data['s5_targets']:
        if t['var'] == 'backend.log.LOG-C1':
            a = answers.get(t['target_id'])
            if a and a.get('decision') == 'yes':
                cap_log[t['repo']] = 'llm'
    # EXT
    for k in EXT_NAME:
        for t in data['s5_targets']:
            if t['var'] == 'backend.extras.' + k:
                a = answers.get(t['target_id'])
                if a and a.get('decision') == 'yes' and not V['backend.extras.' + k]['value']:
                    V['backend.extras.' + k].update(value=True, state='value_llm')
    V['backend.extras']['value'] = sum(1 for k in EXT_NAME if V['backend.extras.' + k]['value'])
    if V['backend.extras']['value'] and V['backend.extras']['state'] == 'zero_unused':
        V['backend.extras']['state'] = 'value_rule'
    if any(V['backend.extras.' + k]['state'] == 'value_llm' for k in EXT_NAME):
        V['backend.extras']['state'] = 'value_llm'

    # ---------------- 변수 LV(점수 ÷ 만점 × 5), 상한, A안·B안
    def var_lv(items, ai_items, caps, all_repos):
        res = {}
        for plan in ('A', 'B'):
            pts = mx = 0
            unknown = []
            mine_pts = 0
            for iid, p in items.items():
                v = V[iid]
                if iid in ai_items and plan == 'A':
                    continue                     # 규칙 13: 승인된 검증기가 없으므로 만점에서 뺌
                if v['state'] == 'not_applicable':
                    continue
                if iid.endswith('API8'):
                    if v.get('value') == 1:
                        pts += 1
                        mx += 1
                        mine_pts += 1
                    continue
                if v['value'] is None:
                    unknown.append(iid.split('.')[-1])
                    continue                     # 모름·대기: 「제안」[B-55] 그 항목을 만점에서 뺌
                pts += v['value']
                mx += p
                if not iid.endswith('LOG1'):
                    mine_pts += v['value']
            lv = (pts / mx * 5) if mx else None
            if lv is not None and mine_pts == 0:
                lv = 0.0                         # 규칙 9: 내 줄로 받은 점수가 없으면 0
            cap = None
            if caps and lv is not None:
                if set(caps) >= set(all_repos):
                    cap = min(CAP_MAX[c] for c in caps.values())
                    lv = min(lv, cap)
            res[plan] = dict(points=pts, max=mx, lv_raw=lv, lv=None if lv is None else round(lv, 1), unknown_items=unknown, cap=cap)
        return res
    allr = data['gate']['passed']
    api_items = {f'backend.api.{k}': p for k, p in API_POINTS.items()}
    log_items = {f'backend.log.{k}': p for k, p in LOG_POINTS.items()}
    api_caps = {k: 'API-C1' for k in cap_api}
    log_caps = {k: 'LOG-C1' for k in cap_log}
    ra = var_lv(api_items, set(), {k: 'API-C1' for k in api_caps}, allr)
    rl = var_lv(log_items, {'backend.log.LOG6'}, {k: 'LOG-C1' for k in log_caps}, allr)
    for vid, nm, r, caps in (('backend.api', 'API·외부 API·캐시', ra, api_caps), ('backend.log', '로그', rl, log_caps)):
        st = 'value_llm' if any(V[i]['state'] == 'value_llm' for i in (api_items if vid == 'backend.api' else log_items)) else 'value_rule'
        if r['B']['lv'] is None:
            st = 'unknown_failed'
        V[vid] = dict(name=nm, role='backend_var', value=r['B']['lv'], state=st, unit='LV(0~5)', by_repo={},
                      instances=[], evidence=[], definition='「문서」 받은 점수(기본 포함) ÷ 만점 × 5(규칙 2). 만점: API 9(외부 호출 0개면 −1, 목록 API 0개면 −1, 캐시 제대로면 +1), 로그 8. '
                                                          '상한은 모든 백엔드 레포에 실수가 있을 때만(규칙 14). 모름·대기 항목은 만점에서 뺌(「제안」[B-55])',
                      notes=f"B안(LLM 값 처음부터 LV, 사용자 결정 2026-11-25) = value. A안(규칙 13: [AI 확인] 항목을 만점에서 뺌) = {r['A']['lv']}",
                      alt={'A안(규칙13)': r['A'], 'B안(LLM 처음부터)': r['B']}, caps_by_repo=caps)
    return data


def finalize(person, data, answers):
    """S5 답을 반영한다. answers = {target_id: {decision, value, evidence, model, rounds}}. 답이 없는 대상은 대기."""
    for t in data.get('s5_targets', []):
        a = answers.get(t['target_id'])
        t['s5'] = dict(status='끝남' if a else '대기', decision=(a or {}).get('decision'), rounds=len((a or {}).get('rounds') or []) if isinstance((a or {}).get('rounds'), list) else (a or {}).get('rounds'))
    compute(data, answers)
    return data


def main():
    for pid in sys.argv[1:]:
        t = time.time()
        P = L.load_person(pid)
        data = extract(P)
        L.write_vars(pid, CAT, data)
        V = data['variables']
        print(pid, f"{time.time() - t:.1f}s", 'repos', data['gate']['passed'] and len(data['gate']['passed']),
              'API', V.get('backend.api', {}).get('value'), 'LOG', V.get('backend.log', {}).get('value'), 'EXT', V.get('backend.extras', {}).get('value'),
              'S5', len(data['s5_targets']), file=sys.stderr)


if __name__ == '__main__':
    main()
