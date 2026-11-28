#!/usr/bin/env python3
"""cat_backend_a용 사본(2026-11-26, 버림용): 옛 owncheck_v2.py(본인 확인 스파이크)를 그대로 옮기고
routes(keep_all=True)로 GET 라우트까지 낼 수 있게만 고쳤다. blobs()는 cat_backend_a가 색인 판으로 바꿔 끼운다.
--- 아래는 원래 설명 ---
스파이크 v2(버림용, 제품 코드 아님): 본인 확인을 '규칙으로 먼저' 판정한다.

1) API 목록: Spring·Nest·Express/Koa/Fastify·Next.js·FastAPI·Flask·Django/DRF 라우트를 찾아 수정·삭제 API를 고른다.
2) 함수 따라가기: 핸들러에서 서비스·헬퍼·저장소 함수까지(최대 4단계) 타입·import로 따라가고,
   로그인 사용자 값이 어느 인자로 넘어가는지(현재 사용자 값 추적)도 같이 넘긴다.
3) 판정: P1 작성자 비교, P2 소유자 조건 조회, P3 소유자 권한 클래스·가드·미들웨어(본문까지 확인), P4 @PreAuthorize 식.
   작성자 칸이 있는 자원인지(엔티티·모델 필드), 내 정보만 다루는 API(/me)인지도 판정한다.
받은 코드는 읽기만 한다(git ls-tree·cat-file). 결과에는 레포 번호만 쓴다.
usage: python3 -I owncheck_v2.py <private_map.json> <out.json> R002 R005 ...
"""
import ast
import collections
import io
import json
import os
import re
import subprocess
import sys
import tokenize

CODE_EXT = ('.java', '.kt', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.py', '.prisma', '.xml')
SKIP = re.compile(r'(^|/)(node_modules|vendor|dist|build|out|target|\.next|\.nuxt|coverage|\.venv|venv|site-packages|__pycache__|test|tests|__tests__|spec|specs|e2e|cypress|mocks?|fixtures?)(/|$)'
                  r'|\.(test|spec)\.[cm]?[jt]sx?$|_test\.py$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt)$|\.min\.js$|\.d\.ts$', re.I)
FRONT = re.compile(r'(^|/)(frontend|front|client|web|fe|mobile|android|ios|components|pages(?!/api)|hooks|store|views)(/|$)', re.I)


def git(d, *a):
    return subprocess.run(['git', '-C', d, *a], capture_output=True).stdout.decode('utf-8', errors='replace')


def blobs(d):
    want = []
    for line in git(d, 'ls-tree', '-r', 'HEAD').splitlines():
        if '\t' not in line: continue
        meta, path = line.split('\t', 1)
        parts = meta.split()
        if len(parts) < 3 or parts[1] != 'blob' or not path.endswith(CODE_EXT) or SKIP.search(path): continue
        want.append((parts[2], path))
    if not want: return {}
    p = subprocess.run(['git', '-C', d, 'cat-file', '--batch'], input=('\n'.join(s for s, _ in want) + '\n').encode(), capture_output=True)
    data, res, i, by = p.stdout, {}, 0, collections.defaultdict(list)
    for s, path in want: by[s].append(path)
    while i < len(data):
        nl = data.find(b'\n', i)
        if nl < 0: break
        h = data[i:nl].decode(errors='replace').split()
        if len(h) < 3 or h[1] != 'blob':
            i = nl + 1
            continue
        size, st = int(h[2]), nl + 1
        if size <= 600_000:
            t = data[st:st + size].decode('utf-8', errors='replace')
            for path in by.get(h[0], []):
                if path.endswith('.xml') and '<mapper' not in t: continue
                res[path] = t
        i = st + size + 1
    return res


def strip_c(src):
    oc, om, i, n = [], [], 0, len(src)
    while i < n:
        ch, nx = src[i], src[i + 1] if i + 1 < n else ''
        if ch == '/' and nx == '/':
            j = src.find('\n', i)
            j = n if j < 0 else j
            oc.append(' ' * (j - i)); om.append(' ' * (j - i)); i = j
            continue
        if ch == '/' and nx == '*':
            j = src.find('*/', i + 2)
            j = n if j < 0 else j + 2
            b = re.sub(r'[^\n]', ' ', src[i:j])
            oc.append(b); om.append(b); i = j
            continue
        if ch in '"\'`':
            j = i + 1
            while j < n:
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == ch:
                    j += 1
                    break
                if ch != '`' and src[j] == '\n': break
                j += 1
            seg = src[i:j]
            oc.append(seg); om.append(seg[0] + re.sub(r'[^\n]', ' ', seg[1:-1]) + seg[-1] if len(seg) >= 2 else seg); i = j
            continue
        oc.append(ch); om.append(ch); i += 1
    return ''.join(oc), ''.join(om)


def strip_py(src):
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception:
        return src
    lines = [list(l) for l in src.splitlines(True)]
    for t in toks:
        if t.type == tokenize.COMMENT:
            (sr, sc), (er, ec) = t.start, t.end
            if sr - 1 < len(lines):
                for c in range(sc, min(ec, len(lines[sr - 1]))): lines[sr - 1][c] = ' '
    return ''.join(''.join(l) for l in lines)


def match(m, k, o, c):
    d = 0
    for x in range(k, len(m)):
        if m[x] == o: d += 1
        elif m[x] == c:
            d -= 1
            if d == 0: return x
    return len(m) - 1


def depth_map(m):
    d, cur = [0] * (len(m) + 1), 0
    for i, ch in enumerate(m):
        d[i] = cur
        if ch == '{': cur += 1
        elif ch == '}': cur = max(0, cur - 1)
    d[len(m)] = cur
    return d


def deco_start(m, lo, pos):
    """(cat_backend_a 고침) pos 앞의 데코레이터·어노테이션 묶음이 시작하기 직전 위치. 괄호 안의 { } ; 는 건너뛴다."""
    pd = bd = 0
    k = pos - 1
    while k > lo:
        ch = m[k]
        if ch == ')':
            pd += 1
        elif ch == '(':
            pd -= 1
        elif ch == '}':
            if pd > 0:
                bd += 1
            else:
                return k
        elif ch == '{':
            if bd > 0:
                bd -= 1
            else:
                return k
        elif ch == ';' and pd == 0:
            return k
        k -= 1
    return lo


def line_of(t, pos):
    return t.count('\n', 0, pos) + 1


def split_top(code, masked, angle=False):
    parts, d, s = [], 0, 0
    op, cl = ('([{<', ')]}>') if angle else ('([{', ')]}')
    for k, ch in enumerate(masked):
        if ch in op: d += 1
        elif ch in cl: d -= 1
        elif ch == ',' and d == 0:
            parts.append((code[s:k], masked[s:k])); s = k + 1
    parts.append((code[s:], masked[s:]))
    return [(c.strip(), m.strip()) for c, m in parts if c.strip()]


OWN_WORDS = (r'(?:author|owner|writer|creator|user|member|seller|host|uploader|poster|company|team|tenant|organization|org|store|shop|workspace|group|club|account|customer|createdBy|created_by|registrant|profile'
             r'|receiver|recipient|sender|requester|buyer|applicant|assignee|reviewer|participant|attendee|leader|captain|publisher|clientCompany|client)')
OWN_SEG = re.compile(r'^(?:get)?' + OWN_WORDS + r'\w*$', re.I)
STOP = set('if for while switch catch return new throw else print println log info warn error debug json status send then map filter forEach push '
           'equals toString isEmpty isPresent orElse orElseThrow orElseGet stream collect of build builder ok created noContent body header '
           'get set put add remove contains size length trim split join replace format valueOf parseInt Number String Object keys values '
           'require import export function async await assert len str int dict list range isinstance getattr setattr hasattr exists super '
           'Response JsonResponse HttpResponse HTTPException Depends Query Path Body render redirect next resolve reject catch finally'.split())
CUR = re.compile(r'\breq(?:uest)?\b\s*(?:as\s+[^)]*\))?\s*[!?]?\s*\.\s*(?:user|userId|user_id|uid|memberId|member|auth|decoded|payload|session\s*\.\s*user)\b|\(\s*req(?:uest)?\s+as\s+[^)]*\)\s*[!?]?\s*\.\s*(?:user|userId|auth|member)\b|\breq(?:uest)?\s*\[\s*[\'"]user[\'"]\s*\]|\bself\s*\.\s*request\s*\.\s*user\b|\bres\s*\.\s*locals\s*\.\s*(?:user|userId|auth|member)\w*|\bctx\s*\.\s*(?:state\s*\.\s*)?user\b'
                 r'|\bcurrent_user\b|\bcurrentUser\b|\bg\s*\.\s*user\b|\bget_jwt_identity\s*\(|\bSecurityContextHolder\b|\b(?:get|find|load|fetch)(?:Current|Login|Logged|Auth|Authenticated|My)(?:User|Member|Account|Id|UserId|MemberId)\w*\s*\('
                 r'|\bSecurityUtils?\s*\.\s*\w+\s*\(|\bAuthUtils?\s*\.\s*\w+\s*\(|\b\w*(?:[Jj]wt|[Tt]oken)\w*\s*\.\s*(?:get|extract|parse|verify|decode)\w*\s*\(|\bjwt\s*\.\s*(?:verify|decode)\s*\('
                 r'|\bauthentication\s*\.\s*get(?:Name|Principal|Details)\s*\(|\bprincipal\s*\.\s*get\w*\s*\(|\bgetServerSession\s*\(|\bsession\s*\.\s*user\b|\bauth\s*\(\s*\)|\buserDetails\s*\.\s*get\w*\s*\(')
J_CUR_ANNO = re.compile(r'@(?:AuthenticationPrincipal|LoginUser|CurrentUser|AuthUser|Login|LoginMember|CurrentMember|AuthMember|UserId|MemberId|RequestAttribute|AuthenticatedUser|LoginId|Auth)\b')
J_CUR_TYPE = re.compile(r'^(?:Principal|Authentication|UserDetails|\w*UserDetails\w*|\w*Principal\w*|LoginUser|AuthUser|SessionUser|CustomUser|JwtAuthentication\w*)$')
TS_CUR_DECO = re.compile(r'@(?:CurrentUser|User|GetUser|AuthUser|ReqUser|LoginUser|Auth|UserId|Member|CurrentMember|GetMember|JwtUser)\s*\(')
TS_REQ_DECO = re.compile(r'@(?:Req|Request)\s*\(')
PY_CUR_DEP = re.compile(r'Depends\s*\(\s*[\w.]*(?:current_?(?:active_?)?user|get_user|current_member|auth|verify|token|login)\w*', re.I)


class Repo:
    def __init__(self, rid, d):
        self.rid, self.d = rid, d
        raw = blobs(d)
        self.files = {}
        for path, txt in raw.items():
            if path.endswith('.py'):
                self.files[path] = ('py', strip_py(txt), None)
            elif path.endswith(('.prisma', '.xml')):
                self.files[path] = (path.rsplit('.', 1)[1], txt, None)
            else:
                c, m = strip_c(txt)
                self.files[path] = ('java' if path.endswith(('.java', '.kt')) else 'ts', c, m)
        self.classes = collections.defaultdict(list)
        self.funcs = collections.defaultdict(list)
        self.file_funcs = collections.defaultdict(lambda: collections.defaultdict(list))
        self.imports = collections.defaultdict(dict)
        self.repo_entity = {}
        self.mybatis = {}
        self.py_mods = {}
        self.unresolved = 0
        for path, (lang, code, masked) in self.files.items():
            try:
                if lang == 'java': self.index_java(path, code, masked)
                elif lang == 'ts': self.index_ts(path, code, masked)
                elif lang == 'py': self.index_py(path, code)
                elif lang == 'xml': self.index_xml(code)
            except RecursionError:
                pass

    # ---------- Java ----------
    def index_java(self, path, code, masked):
        dm = depth_map(masked)
        kotlin = path.endswith('.kt')
        for mo in re.finditer(r'\b(class|interface|enum|record|object)\s+([A-Z]\w*)', masked):
            b = masked.find('{', mo.end())
            if b < 0: continue
            hdr = masked[mo.end():b]
            if ';' in hdr or (kotlin and re.search(r'\bfun\b|\bclass\b', hdr)): continue
            e = match(masked, b, '{', '}')
            p = deco_start(masked, -1, mo.start())
            cls = dict(lang='java', file=path, name=mo.group(2), kind=mo.group(1), header=code[mo.end():b], annos=code[p + 1:mo.start()],
                       start=b, end=e, depth=dm[b] + 1, fields={}, methods=collections.defaultdict(list))
            if kotlin:
                for fm in re.finditer(r'(?:val|var)\s+(\w+)\s*:\s*([A-Z][\w.]*(?:<[^>]*>)?)', code[mo.end():b]): cls['fields'][fm.group(1)] = fm.group(2)
            rm = re.search(r'(?:Jpa|Crud|PagingAndSorting|Mongo|ReactiveCrud|ReactiveMongo|Elasticsearch|ListCrud)Repository\s*<\s*(\w+)', cls['header'])
            if rm: self.repo_entity[cls['name']] = rm.group(1)
            for fm in re.finditer(r'(?:(?:private|protected|public|static|final|transient|volatile|lateinit|val|var)\s+)+([A-Za-z]\w*)\s*(?::\s*)?([A-Z][\w.]*(?:\s*<[^;=(){}]*>)?(?:\[\])?)?\s*(?:([a-z]\w*))?\s*(?=[;=\n])', masked[b + 1:e]):
                pos = b + 1 + fm.start()
                if dm[pos] != cls['depth']: continue
                if fm.group(3) and fm.group(2):
                    cls['fields'][fm.group(3)] = fm.group(2)
            for fm in re.finditer(r'(?:(?:private|protected|public|static|final|transient|volatile)\s+)+([A-Z][\w.]*(?:\s*<[^;=(){}]*>)?(?:\[\])?)\s+([a-z]\w*)\s*(?=[;=])', masked[b + 1:e]):
                if dm[b + 1 + fm.start()] == cls['depth']: cls['fields'][fm.group(2)] = fm.group(1)
            self.classes[cls['name']].append(cls)
            for mm in re.finditer(r'\b([a-z_]\w*)\s*\(', masked[b + 1:e]):
                pos = b + 1 + mm.start()
                if dm[pos] != cls['depth']: continue
                name = mm.group(1)
                if name in ('if', 'for', 'while', 'switch', 'catch', 'synchronized', 'return', 'new', 'throw', 'else', 'super', 'this'): continue
                pre = masked[:pos].rstrip()
                if pre.endswith('.'): continue
                p2 = deco_start(masked, b, pos)
                prefix = masked[p2 + 1:pos]
                pm = re.sub(r'@\w+(?:\.\w+)*(?:\s*\((?:[^()]|\([^()]*\))*\))?', ' ', prefix)
                if '=' in pm: continue
                if kotlin:
                    if not re.search(r'\bfun\s+(?:<[^>]*>\s*)?$', pm): continue
                elif not re.search(r'[\w>\]?]\s+$', pm) or re.match(r'\s*(return|new|throw|else|case)\b', pm):
                    continue
                q = match(masked, b + 1 + mm.end() - 1, '(', ')')
                rest = masked[q + 1:q + 300]
                mt = re.match(r'\s*(?::\s*[\w.<>?, ]+)?\s*(?:throws\s+[\w.,\s<>]+)?\s*(\{|;|=)', rest)
                if not mt: continue
                params = self.java_params(code[b + 1 + mm.end():q], masked[b + 1 + mm.end():q], kotlin)
                if mt.group(1) == '{':
                    bb = q + 1 + mt.end() - 1
                    be = match(masked, bb, '{', '}')
                    fc, fmk = code[p2 + 1:be + 1], masked[p2 + 1:be + 1]
                else:
                    fc, fmk = code[p2 + 1:q + 1], masked[p2 + 1:q + 1]
                f = dict(lang='java', file=path, cls=cls['name'], name=name, params=params, code=fc, masked=fmk, line=line_of(masked, pos), annos=code[p2 + 1:pos])
                cls['methods'][name].append(f)
                self.funcs[name].append(f)
                self.file_funcs[path][name].append(f)

    @staticmethod
    def java_params(pc, pm, kotlin=False):
        out = []
        for c, m in split_top(pc, pm, angle=True):
            if kotlin:
                mo = re.match(r'^((?:@[\w.]+(?:\s*\([^)]*\))?\s*)*)(?:val\s+|var\s+)?(\w+)\s*:\s*([\w.<>?, \[\]]+)', c, re.S)
                if mo: out.append((mo.group(1), mo.group(3).strip(), mo.group(2)))
                continue
            mo = re.match(r'^((?:@[\w.]+(?:\s*\((?:[^()]|\([^()]*\))*\))?\s*|final\s+)*)([\w.<>\[\]?,\s]+?)\s+(\w+)$', c, re.S)
            if mo: out.append((mo.group(1), mo.group(2).strip(), mo.group(3)))
            else: out.append(('', '', c.split()[-1] if c.split() else ''))
        return out

    # ---------- TS / JS ----------
    def index_ts(self, path, code, masked):
        dm = depth_map(masked)
        for mo in re.finditer(r'\bclass\s+([A-Z][\w$]*)', masked):
            b = masked.find('{', mo.end())
            if b < 0: continue
            e = match(masked, b, '{', '}')
            p = deco_start(masked, -1, mo.start())
            cls = dict(lang='ts', file=path, name=mo.group(1), kind='class', header=code[mo.end():b], annos=code[p + 1:mo.start()],
                       start=b, end=e, depth=dm[b] + 1, fields={}, methods=collections.defaultdict(list))
            self.classes[cls['name']].append(cls)
            for mm in re.finditer(r'(?:(?:public|private|protected|static|async|readonly|override|get|set)\s+)*([A-Za-z_$][\w$]*)\s*(?:<[^>()]*>)?\s*\(', masked[b + 1:e]):
                pos = b + 1 + mm.start(1)
                if dm[pos] != cls['depth']: continue
                name = mm.group(1)
                if name in ('if', 'for', 'while', 'switch', 'catch', 'return', 'async', 'await', 'function', 'super', 'new', 'typeof'): continue
                if masked[:pos].rstrip().endswith(('.', '=', '(', ',', '?', ':', '!', '&', '|')): continue
                q = match(masked, b + 1 + mm.end() - 1, '(', ')')
                rest = masked[q + 1:q + 300]
                mt = re.match(r'\s*(?::\s*[^{;=]+?)?\s*\{', rest)
                if not mt: continue
                bb = q + 1 + mt.end() - 1
                be = match(masked, bb, '{', '}')
                p2 = deco_start(masked, b, pos)
                params = self.ts_params(code[b + 1 + mm.end():q], masked[b + 1 + mm.end():q])
                f = dict(lang='ts', file=path, cls=cls['name'], name=name, params=params, code=code[p2 + 1:be + 1], masked=masked[p2 + 1:be + 1], line=line_of(masked, pos), annos=code[p2 + 1:pos])
                cls['methods'][name].append(f)
                self.funcs[name].append(f)
                self.file_funcs[path][name].append(f)
                if name == 'constructor':
                    for deco, typ, pname, mod in params:
                        if mod: cls['fields'][pname] = typ
            for fm in re.finditer(r'(?:(?:private|public|protected|readonly)\s+)+([A-Za-z_$][\w$]*)\s*[!?]?\s*:\s*([A-Za-z_$][\w$.]*(?:<[^;=]*>)?)', masked[b + 1:e]):
                if dm[b + 1 + fm.start()] == cls['depth']: cls['fields'][fm.group(1)] = fm.group(2)
            for fm in re.finditer(r'([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^()]*)\)\s*(?::[^=>{]+)?=>\s*\{', masked[b + 1:e]):
                pos = b + 1 + fm.start()
                if dm[pos] != cls['depth']: continue
                bb = b + 1 + fm.end() - 1
                be = match(masked, bb, '{', '}')
                f = dict(lang='ts', file=path, cls=cls['name'], name=fm.group(1), params=self.ts_params(code[b + 1 + fm.start(2):b + 1 + fm.end(2)], fm.group(2)),
                         code=code[pos:be + 1], masked=masked[pos:be + 1], line=line_of(masked, pos), annos='')
                cls['methods'][fm.group(1)].append(f); self.funcs[fm.group(1)].append(f); self.file_funcs[path][fm.group(1)].append(f)
        rx = [re.compile(r'(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*(?:<[^>()]*>)?\s*\('),
              re.compile(r'(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:[\w$.]+\s*\(\s*)?(?:async\s*)?(?:function\s*[\w$]*\s*)?(\()'),
              re.compile(r'(?:exports|module\.exports)\s*\.\s*([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\s*[\w$]*\s*)?(\()'),
              re.compile(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?(?:function\s*[\w$]*\s*)?(\()'),
              re.compile(r'(?<![\w$.])(?:async\s+)([A-Za-z_$][\w$]*)\s*(\()')]
        for i, r in enumerate(rx):
            for mo in r.finditer(masked):
                name = mo.group(1)
                if name in STOP or name in ('if', 'for', 'while', 'switch', 'catch', 'function', 'async'): continue
                ps = mo.end() - 1 if i == 0 else mo.start(2)
                if masked[ps] != '(': continue
                q = match(masked, ps, '(', ')')
                rest = masked[q + 1:q + 300]
                mt = re.match(r'\s*(?::\s*[^{;=]+?)?\s*(?:=>\s*)?\{', rest)
                if not mt: continue
                bb = q + 1 + mt.end() - 1
                be = match(masked, bb, '{', '}')
                if any(f['file'] == path and abs(f['line'] - line_of(masked, mo.start())) <= 1 for f in self.funcs.get(name, [])): continue
                f = dict(lang='ts', file=path, cls=None, name=name, params=self.ts_params(code[ps + 1:q], masked[ps + 1:q]), code=code[mo.start():be + 1],
                         masked=masked[mo.start():be + 1], line=line_of(masked, mo.start()), annos='')
                self.funcs[name].append(f); self.file_funcs[path][name].append(f)
        imp = self.imports[path]
        for mo in re.finditer(r'import\s+(?:type\s+)?(?:([A-Za-z_$][\w$]*)\s*,?\s*)?(?:\{([^}]*)\}|\*\s+as\s+([A-Za-z_$][\w$]*))?\s*from\s*[\'"]([^\'"]+)[\'"]', code):
            spec = mo.group(4)
            if mo.group(1): imp[mo.group(1)] = (spec, 'default')
            if mo.group(3): imp[mo.group(3)] = (spec, '*')
            for it in (mo.group(2) or '').split(','):
                it = it.strip()
                if not it: continue
                a = re.split(r'\s+as\s+', it)
                imp[a[-1].strip()] = (spec, a[0].strip())
        for mo in re.finditer(r'(?:const|let|var)\s+(?:([A-Za-z_$][\w$]*)|\{([^}]*)\})\s*=\s*require\(\s*[\'"]([^\'"]+)[\'"]\s*\)', code):
            if mo.group(1): imp[mo.group(1)] = (mo.group(3), '*')
            for it in (mo.group(2) or '').split(','):
                it = it.strip()
                if it:
                    a = re.split(r'\s*:\s*', it)
                    imp[a[-1].strip()] = (mo.group(3), a[0].strip())

    @staticmethod
    def ts_params(pc, pm):
        out = []
        for c, m in split_top(pc, pm):
            mo = re.match(r'^((?:@[\w$.]+\s*\((?:[^()]|\([^()]*\))*\)\s*)*)((?:(?:private|public|protected|readonly)\s+)*)(?:\.\.\.)?([A-Za-z_$][\w$]*|\{[^}]*\})\s*\??\s*(?::\s*(.+?))?\s*(?:=.*)?$', c, re.S)
            if mo: out.append((mo.group(1), (mo.group(4) or '').strip(), mo.group(3), bool(mo.group(2).strip())))
            else: out.append(('', '', c, False))
        return out

    # ---------- Python ----------
    def index_py(self, path, code):
        mod = path[:-3].replace('/', '.')
        if mod.endswith('.__init__'): mod = mod[:-9]
        self.py_mods[mod] = path
        try:
            tree = ast.parse(code)
        except Exception:
            return
        imp = self.imports[path]
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = ('.' * node.level) + (node.module or '')
                for a in node.names: imp[a.asname or a.name] = (base, a.name)
            elif isinstance(node, ast.Import):
                for a in node.names: imp[a.asname or a.name.split('.')[0]] = (a.name, '*')

        def mkf(fn, cls):
            seg = ast.get_source_segment(code, fn) or ''
            params = []
            args = fn.args.args + fn.args.kwonlyargs
            defaults = [None] * (len(fn.args.args) - len(fn.args.defaults)) + list(fn.args.defaults) + list(fn.args.kw_defaults)
            for a, dflt in zip(args, defaults):
                ann = ast.get_source_segment(code, a.annotation) if a.annotation is not None else ''
                dv = ast.get_source_segment(code, dflt) if dflt is not None else ''
                params.append((dv or '', ann or '', a.arg))
            decos = '\n'.join('@' + (ast.get_source_segment(code, d_) or '') for d_ in fn.decorator_list)
            return dict(lang='py', file=path, cls=cls, name=fn.name, params=params, code=seg, masked=seg, line=fn.lineno, annos=decos, node=fn)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f = mkf(node, None)
                self.funcs[node.name].append(f); self.file_funcs[path][node.name].append(f)
            elif isinstance(node, ast.ClassDef):
                cls = dict(lang='py', file=path, name=node.name, kind='class', header=', '.join(ast.get_source_segment(code, b) or '' for b in node.bases),
                           annos='', code=ast.get_source_segment(code, node) or '', fields={}, methods=collections.defaultdict(list), assigns={}, line=node.lineno)
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        f = mkf(sub, node.name)
                        cls['methods'][sub.name].append(f); self.funcs[sub.name].append(f); self.file_funcs[path][sub.name].append(f)
                    elif isinstance(sub, ast.Assign):
                        for t in sub.targets:
                            if isinstance(t, ast.Name): cls['assigns'][t.id] = ast.get_source_segment(code, sub.value) or ''
                    elif isinstance(sub, ast.ClassDef) and sub.name == 'Meta':
                        for s2 in sub.body:
                            if isinstance(s2, ast.Assign):
                                for t in s2.targets:
                                    if isinstance(t, ast.Name): cls['assigns']['Meta.' + t.id] = ast.get_source_segment(code, s2.value) or ''
                self.classes[node.name].append(cls)

    def index_xml(self, code):
        for mo in re.finditer(r'<(select|update|delete|insert)\s+[^>]*\bid\s*=\s*"(\w+)"[^>]*>(.*?)</\1>', code, re.S):
            self.mybatis[mo.group(2)] = mo.group(3)

    # ---------- 이름 풀기 ----------
    def resolve_ts_module(self, from_file, spec):
        if spec.startswith('.'):
            base = os.path.normpath(os.path.join(os.path.dirname(from_file), spec))
        elif spec.startswith(('@/', '~/', 'src/', '@src/')):
            base = re.sub(r'^(@/|~/|@src/)', 'src/', spec)
        else:
            return None
        cands = [base]
        if base.endswith(('.js', '.jsx', '.mjs', '.cjs')): cands.append(base.rsplit('.', 1)[0])
        for c in cands:
            for ext in ('', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '/index.ts', '/index.js'):
                if c + ext in self.files: return c + ext
        tail = base.split('src/', 1)[-1]
        for f in self.files:
            for ext in ('.ts', '.tsx', '.js', '.jsx', '/index.ts', '/index.js'):
                if f.endswith('/' + tail + ext) or f == tail + ext: return f
        return None

    def resolve_py_module(self, from_file, base):
        if base.startswith('.'):
            lvl = len(base) - len(base.lstrip('.'))
            pkg = from_file.split('/')[:-1]
            pkg = pkg[:len(pkg) - (lvl - 1)] if lvl > 1 else pkg
            name = base.lstrip('.')
            mod = '.'.join(pkg + ([name] if name else []))
        else:
            mod = base
        if mod in self.py_mods: return self.py_mods[mod]
        for m, p in self.py_mods.items():
            if m.endswith('.' + mod) or m == mod: return p
        return None

    @staticmethod
    def has_body(f):
        return f['lang'] == 'py' or '{' in (f.get('masked') or '')[len(f.get('annos') or ''):]

    def class_methods(self, cname, mname, seen=None):
        seen = seen or set()
        out = []
        for cls in self.classes.get(cname, []):
            if (cls['file'], cname) in seen: continue
            seen.add((cls['file'], cname))
            out += cls['methods'].get(mname, [])
            for base in re.findall(r'\b([A-Z]\w*)', cls.get('header', '')):
                if base != cname and base in self.classes and not out: out += self.class_methods(base, mname, seen)
        bodied = [f for f in out if self.has_body(f)]
        if out and not bodied:
            out = []
        else:
            out = bodied
        if not out:
            for cls_list in self.classes.values():
                for cls in cls_list:
                    if re.search(r'\b(?:implements|extends)\b[^{]*\b' + re.escape(cname) + r'\b', cls.get('header', '')) or re.search(r':\s*[^{]*\b' + re.escape(cname) + r'\b', cls.get('header', '')):
                        out += cls['methods'].get(mname, [])
            for cls in self.classes.get(cname + 'Impl', []): out += cls['methods'].get(mname, [])
        return out

    def var_type(self, f, var):
        if f['lang'] == 'java':
            for an, t, n in f['params']:
                if n == var: return t
            mo = re.search(r'\b([A-Z][\w.]*(?:<[^;=()]*>)?)\s+' + re.escape(var) + r'\s*=', f['masked'])
            if mo: return mo.group(1)
            mo = re.search(r'\b(?:val|var)\s+' + re.escape(var) + r'\s*:\s*([A-Z][\w.]*(?:<[^>]*>)?)', f['masked'])
            if mo: return mo.group(1)
            for cls in self.classes.get(f['cls'] or '', []):
                if var in cls['fields']: return cls['fields'][var]
        elif f['lang'] == 'ts':
            for deco, t, n, mod in f['params']:
                if n == var: return t
            mo = re.search(r'\b(?:const|let|var)\s+' + re.escape(var) + r'\s*(?::\s*([A-Za-z_$][\w$.<>]*))?\s*=\s*new\s+([A-Z][\w$]*)', f['code'])
            if mo: return mo.group(1) or mo.group(2)
            for cls in self.classes.get(f['cls'] or '', []):
                if var in cls['fields']: return cls['fields'][var]
        return None

    @staticmethod
    def base_type(t):
        t = re.sub(r'<.*', '', t or '').strip().split('.')[-1]
        return t

    def resolve_call(self, f, recv, name, this):
        """(받는 쪽, 함수 이름) → 후보 함수들"""
        out = []
        if f['lang'] == 'java':
            if recv is None or recv == 'this':
                if f['cls']: out = self.class_methods(f['cls'], name)
            elif recv[0].isupper():
                out = self.class_methods(recv, name)
            else:
                t = self.var_type(f, recv)
                if t: out = self.class_methods(self.base_type(t), name)
        elif f['lang'] == 'ts':
            imp = self.imports.get(f['file'], {})
            if this and recv:
                t = None
                for cls in self.classes.get(f['cls'] or '', []):
                    t = cls['fields'].get(recv) or t
                if t: out = self.class_methods(self.base_type(t), name)
            elif this:
                if f['cls']: out = self.class_methods(f['cls'], name)
            elif recv:
                if recv in imp:
                    mp = self.resolve_ts_module(f['file'], imp[recv][0])
                    if mp: out = self.file_funcs[mp].get(name, [])
                    if not out and imp[recv][1] not in ('*', 'default'): out = self.class_methods(imp[recv][1], name)
                    if not out and mp:
                        for cls_list in self.classes.values():
                            for cls in cls_list:
                                if cls['file'] == mp: out += cls['methods'].get(name, [])
                elif recv[0].isupper():
                    out = self.class_methods(recv, name)
                else:
                    t = self.var_type(f, recv)
                    if t: out = self.class_methods(self.base_type(t), name)
            else:
                out = self.file_funcs[f['file']].get(name, [])
                if not out and name in imp:
                    mp = self.resolve_ts_module(f['file'], imp[name][0])
                    if mp: out = self.file_funcs[mp].get(imp[name][1] if imp[name][1] not in ('*', 'default') else name, []) or self.file_funcs[mp].get(name, [])
        elif f['lang'] == 'py':
            imp = self.imports.get(f['file'], {})
            if recv == 'self' and f['cls']:
                out = self.class_methods(f['cls'], name)
            elif recv:
                if recv in imp:
                    mp = self.resolve_py_module(f['file'], imp[recv][0] if imp[recv][1] == '*' else imp[recv][0] + '.' + imp[recv][1])
                    if not mp: mp = self.resolve_py_module(f['file'], imp[recv][0])
                    if mp: out = self.file_funcs[mp].get(name, [])
                    if not out: out = self.class_methods(imp[recv][1] if imp[recv][1] != '*' else recv, name)
                elif recv[:1].isupper():
                    out = self.class_methods(recv, name)
            else:
                out = self.file_funcs[f['file']].get(name, [])
                if not out and name in imp:
                    mp = self.resolve_py_module(f['file'], imp[name][0])
                    if mp: out = self.file_funcs[mp].get(imp[name][1], [])
        if not out and name not in STOP:
            cands = self.funcs.get(name, [])
            if 0 < len(cands) <= 2: out = cands
            elif cands: self.unresolved += 1
        return [g for g in out if g is not f][:4]


SVC_RECV = re.compile(r'(?i)(service|repository|repo|dao|mapper|manager|facade|usecase|port|adapter|handler|client|model|store)$')  # (cat_backend_a 고침) 서비스 받는 쪽이면 STOP 이름도 따라감
CALL_C = re.compile(r'(?:(this)\s*\.\s*)?(?:([A-Za-z_$][\w$]*)\s*\??\.\s*)?([A-Za-z_$][\w$]*)\s*(?:<[^>()]*>)?\s*\(')
CALL_PY = re.compile(r'(?:([A-Za-z_][\w]*)\s*\.\s*)?([A-Za-z_][\w]*)\s*\(')


def calls_of(f):
    """함수 본문에서 부르는 곳: (받는 쪽, 이름, this 여부, 인자 목록)"""
    out = []
    if f['lang'] == 'py':
        node = f.get('node')
        if node is None: return out
        src = f['code']
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                fn = n.func
                recv, name = None, None
                if isinstance(fn, ast.Attribute):
                    name = fn.attr
                    if isinstance(fn.value, ast.Name): recv = fn.value.id
                    elif isinstance(fn.value, ast.Attribute) and isinstance(fn.value.value, ast.Name) and fn.value.value.id == 'self': recv = 'self.' + fn.value.attr
                    else: recv = '?'
                elif isinstance(fn, ast.Name):
                    name = fn.id
                if not name or (name in STOP and not (recv and SVC_RECV.search(str(recv)))): continue
                args = [ast.unparse(a) for a in n.args] + [f'{k.arg}={ast.unparse(k.value)}' for k in n.keywords]
                out.append((recv if recv != '?' else None, name, False, args, n.lineno - node.lineno + 1))
        return out
    m, c = f['masked'], f['code']
    for mo in CALL_C.finditer(m):
        this, recv, name = mo.group(1), mo.group(2), mo.group(3)
        if (name in STOP and not (recv and SVC_RECV.search(recv))) or name in ('if', 'for', 'while', 'switch', 'catch', 'function', 'return', 'typeof', 'new'): continue
        if mo.start() > 0 and m[mo.start() - 1] in '.)' and not this and not recv: continue
        if recv and m[max(0, mo.start() - 1)] == '.': recv = None
        p = mo.end() - 1
        q = match(m, p, '(', ')')
        args = [a for a, _ in split_top(c[p + 1:q], m[p + 1:q])]
        out.append((recv, name, bool(this), args, line_of(m, mo.start())))
    return out[:80]


def param_compares(g):
    """g가 자기 매개변수 둘을 서로 비교하는 곳: [(i, j)]"""
    names = [p[2] for p in g['params']] if g['lang'] != 'py' else [p[2] for p in g['params'] if p[2] not in ('self', 'cls')]
    if len(names) < 2: return []
    pos = {n: k for k, n in enumerate(names) if n and re.match(r'^[A-Za-z_$][\w$]*$', n)}
    found = []
    m, c = g['masked'], g['code']
    for mo in CMP.finditer(m):
        op = mo.group(0)
        if op.startswith('Objects'):
            q = match(m, mo.end() - 1, '(', ')')
            parts = [a for a, _ in split_top(c[mo.end():q], m[mo.end():q])]
            if len(parts) < 2: continue
            l, r = parts[0], parts[1]
        elif op.startswith(('.equals', '.eq', '.ne')):
            q = match(m, mo.end() - 1, '(', ')')
            r, l = c[mo.end():q], side(m, c, mo.start(), True)
        else:
            l, r = side(m, c, mo.start(), True), side(m, c, mo.end(), False)
        lb = re.match(r'^\W*([A-Za-z_$][\w$]*)', l.strip().lstrip('!('))
        rb = re.match(r'^\W*([A-Za-z_$][\w$]*)', r.strip().lstrip('!('))
        if lb and rb and lb.group(1) in pos and rb.group(1) in pos and lb.group(1) != rb.group(1):
            found.append((pos[lb.group(1)], pos[rb.group(1)]))
    return found


USERISH_ACC = r'\s*\??\.\s*(?:get)?(?:user|member|clientUser|loginUser|currentUser|me|principal|account|requester|writer|author|owner|uid|userId|memberId)\w*'


def mentions(expr, vs):
    for v in vs:
        if '.' in v:
            if re.search(r'\b' + re.escape(v) + r'\b', expr): return True
        elif re.search(r'(?<![\w$.])' + re.escape(v) + r'\b', expr):
            return True
    return False


def is_tainted(expr, tv, cv=()):
    """로그인 사용자 값(또는 그 id)인가"""
    if CUR.search(expr): return True
    if mentions(expr, tv): return True
    for c in cv:
        if re.search(r'(?<![\w$.])' + re.escape(c) + USERISH_ACC, expr, re.I): return True
    return False


def classify(rhs, tv, cv):
    if is_tainted(rhs, tv, cv):
        sv = re.match(r'^\s*\(?\s*(?:\([^)]*\)\s*)?([A-Za-z_$][\w$]*)\b', rhs.strip())
        starts_user = bool(sv) and sv.group(1) != 'new' and (sv.group(1) in tv or CUR.match(rhs.strip()) is not None)
        if not starts_user and re.search(r'\bnew\s+[A-Z]\w*\s*\(|\.builder\s*\(\s*\)|\b[A-Z]\w*\s*\.\s*(?:of|from|create|builder)\s*\(', rhs):
            return 'carrier'
        return 'strong'
    if mentions(rhs, cv) and re.search(r'\bnew\s+[A-Z]\w*\s*\(|\.builder\s*\(\s*\)|\b[A-Z]\w*\s*\.\s*(?:of|from|create)\s*\(', rhs):
        return 'carrier'
    return None


def taint_vars(f, tps, tpc=frozenset()):
    tv, cv = set(tps), set(tpc)
    if f['lang'] == 'java':
        for an, t, n in f['params']:
            if J_CUR_ANNO.search(an or '') or J_CUR_TYPE.match(Repo.base_type(t)): tv.add(n)
    elif f['lang'] == 'ts':
        for deco, t, n, mod in f['params']:
            if TS_CUR_DECO.search(deco or ''): tv.add(n)
            if TS_REQ_DECO.search(deco or ''): tv.add(n + '.user')
    elif f['lang'] == 'py':
        for dv, ann, n in f['params']:
            if PY_CUR_DEP.search(dv or '') or PY_CUR_DEP.search(ann or ''): tv.add(n)
    body = f['code']
    for _ in range(3):
        for mo in re.finditer(r'(?:\b(?:final|const|let|var|val)\s+)?(?:[A-Z][\w.<>\[\]?,]*\s+)?\b([A-Za-z_$][\w$]*)\s*(?::\s*[\w$.<>\[\]?]+)?\s*=(?!=)\s*([^;\n]+)', body):
            lhs, rhs = mo.group(1), mo.group(2)
            if lhs in tv: continue
            k = classify(rhs, tv, cv)
            if k == 'strong': tv.add(lhs); cv.discard(lhs)
            elif k == 'carrier' and lhs not in cv: cv.add(lhs)
        for mo in re.finditer(r'(?:const|let|var)\s*\{([^}]*)\}\s*=\s*([^;\n]+)', body):
            if is_tainted(mo.group(2), tv, cv):
                for it in mo.group(1).split(','):
                    it = it.split(':')[-1].strip()
                    if it: tv.add(it)
    return tv, cv


def ownerish(expr, tv):
    for mo in re.finditer(r'(?<![\w$.])([A-Za-z_$][\w$]*)((?:\s*\??\.\s*[A-Za-z_$][\w$]*(?:\s*\(\s*\))?)+)', expr):
        base = mo.group(1)
        if base in tv or base[0].isupper() or base in ('req', 'request', 'res', 'ctx', 'session', 'g', 'principal', 'authentication', 'jwt', 'token'): continue
        if base == 'self' and re.match(r'\s*\.\s*request\b', mo.group(2)): continue
        segs = [re.sub(r'\(\s*\)', '', x).strip() for x in re.split(r'\??\.', mo.group(2)) if x.strip()]
        if any(OWN_SEG.match(x) and not x.isupper() for x in segs): return True
    mo = re.search(r'\b(?:author|owner|writer|creator|user|member|company|receiver|sender)_?[Ii]d\b', expr)
    if mo and not mentions(expr[mo.start():mo.end()], tv): return True
    return False


CMP = re.compile(r'!==|===|!=|==|\.equals\s*\(|\bis\s+not\b|\bis\b|Objects\s*\.\s*equals\s*\(|\.eq\s*\(|\.ne\s*\(')


def side(m, c, pos, back):
    d, k, n, lim = 0, pos, len(m), 220
    if back:
        k = pos - 1
        while k >= 0 and pos - k < lim:
            ch = m[k]
            if ch in ')]': d += 1
            elif ch in '([':
                if d == 0: break
                d -= 1
            elif d == 0 and (ch in '{};,?' or m[max(0, k - 1):k + 1] in ('&&', '||') or (ch == '\n' and m[k - 1:k] != '.')): break
            k -= 1
        return c[k + 1:pos]
    while k < n and k - pos < lim:
        ch = m[k]
        if ch in '([': d += 1
        elif ch in ')]':
            if d == 0: break
            d -= 1
        elif d == 0 and (ch in '{};,?' or m[k:k + 2] in ('&&', '||') or (ch == '\n' and m[k + 1:k + 2] != '.')): break
        k += 1
    return c[pos:k]


def find_p1(f, tv, cv=()):
    m, c = f['masked'], f['code']
    for mo in CMP.finditer(m):
        op = mo.group(0)
        if op.startswith('Objects'):
            q = match(m, mo.end() - 1, '(', ')')
            parts = [a for a, _ in split_top(c[mo.end():q], m[mo.end():q])]
            if len(parts) < 2: continue
            l, r = parts[0], parts[1]
        elif op.startswith(('.equals', '.eq', '.ne')):
            q = match(m, mo.end() - 1, '(', ')')
            r, l = c[mo.end():q], side(m, c, mo.start(), True)
        else:
            l, r = side(m, c, mo.start(), True), side(m, c, mo.end(), False)
        if (is_tainted(l, tv, cv) and ownerish(r, tv)) or (is_tainted(r, tv, cv) and ownerish(l, tv)):
            return line_of(m, mo.start())
    return None


P2_J = re.compile(r'\b([A-Za-z_]\w*)\s*\.\s*([a-z]\w*By\w*?(?:User|Member|Author|Owner|Writer|Creator|Company|Team|Store|Shop|Workspace|Organization|Tenant|Seller|Host|Account|Customer)\w*)\s*\(')
OWN_KEY = r'(?:userId|authorId|ownerId|memberId|writerId|creatorId|companyId|sellerId|accountId|customerId|createdBy|user_id|author_id|owner_id|member_id|writer_id|creator_id|company_id|user|author|owner|member|writer|creator|company)'


def find_p2(f, tv, repo, cv=()):
    m, c = f['masked'], f['code']
    if f['lang'] == 'java':
        for mo in P2_J.finditer(m):
            q = match(m, mo.end() - 1, '(', ')')
            # (cat_backend_a 고침) 인자가 2개 이상(대상 번호 + 로그인 사용자)일 때만: 로그인 사용자 하나로 찾는 것은 '내 것 불러오기'
            parts = [x for x, _ in split_top(c[mo.end():q], m[mo.end():q])]
            if len(parts) >= 2 and any(is_tainted(x, tv, cv) for x in parts) and any(not is_tainted(x, tv, cv) for x in parts): return line_of(m, mo.start())
        for mo in re.finditer(r'\b([a-z]\w*)\s*\.\s*((?:find|exists|delete|get|remove)\w*ById)\s*\(', m):
            q = match(m, mo.end() - 1, '(', ')')
            a = c[mo.end():q]
            parts = [x for x, _ in split_top(a, m[mo.end():q])]
            if len(parts) >= 2 and any(is_tainted(x, tv, cv) or mentions(x, cv) for x in parts) and any(not is_tainted(x, tv, cv) for x in parts): return line_of(m, mo.start())
        for mo in re.finditer(r'\b([a-z]\w*)\s*\.\s*(\w+)\s*\(', m):
            q = match(m, mo.end() - 1, '(', ')')
            if not is_tainted(c[mo.end():q], tv, cv): continue
            sql = repo.mybatis.get(mo.group(2), '')
            t = repo.var_type(f, mo.group(1))
            if t:
                for cls in repo.classes.get(repo.base_type(t), []):
                    for g in cls['methods'].get(mo.group(2), []):
                        sql += ' ' + (g.get('annos', '') or '') + ' ' + (g.get('code', '') or '')
            if re.search(r'(?i)\b(?:user|member|author|owner|writer|creator|company)\w*?(?:_id|Id|\.id)\s*=\s*[#:$]', sql): return line_of(m, mo.start())
        return None
    if f['lang'] == 'ts':
        for mo in re.finditer(r'\b(?:where|filter|query|conditions?)\s*:\s*\{|\.(?:findOne|findFirst|findUnique|findOneAndUpdate|findOneAndDelete|findOneAndRemove|deleteOne|deleteMany|updateOne|updateMany|find|count|countDocuments|exists|findOneBy|findBy|delete|update)\s*\(\s*\{', m):
            b = mo.end() - 1
            e = match(m, b, '{', '}')
            obj_c = c[b:e + 1]
            for km in re.finditer(r'(?<![\w$])' + OWN_KEY + r'\s*(?::\s*(\{[^{}]*\}|[^,}\n]+))?', obj_c):
                key = km.group(0).split(':')[0].strip()
                val = km.group(1) if km.group(1) is not None else key
                if is_tainted(val, tv, cv): return line_of(m, mo.start())
        for mo in re.finditer(r'\.(?:and)?[Ww]here\s*\(\s*[\'"`][^\'"`]*\b(?:user|author|owner|member|writer|creator|company)\w*(?:Id|_id|\.id)\s*=\s*:\s*(\w+)', c):
            if is_tainted(c[mo.start():mo.start() + 400], tv, cv) or mo.group(1) in tv: return line_of(c, mo.start())
        return None
    if f['lang'] == 'py':
        node = f.get('node')
        if node is None: return None
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                fname = n.func.attr if isinstance(n.func, ast.Attribute) else (n.func.id if isinstance(n.func, ast.Name) else '')
                if fname in ('filter', 'get', 'filter_by', 'get_object_or_404', 'get_or_404', 'first_or_404', 'exclude', 'update', 'delete', 'select', 'where', 'find_one', 'delete_one', 'update_one'):
                    for kw in n.keywords:
                        if kw.arg and re.match(r'^(?:owner|user|author|writer|member|creator|company|created_by|receiver|sender)(?:_id)?(?:__\w+)?$', kw.arg) and is_tainted(ast.unparse(kw.value), tv, cv):
                            return n.lineno - node.lineno + 1
                    for a in n.args:
                        s = ast.unparse(a)
                        if re.search(r'\.(?:owner|user|author|writer|member|creator|company|receiver|sender)(?:_id)?\s*==', s) and is_tainted(s, tv, cv): return n.lineno - node.lineno + 1
        return None


P4 = re.compile(r'@(?:Pre|Post)Authorize\s*\(\s*"([^"]*)"')


def find_p4(f):
    for mo in P4.finditer(f.get('annos', '') or ''):
        e = mo.group(1)
        if re.search(r'(?i)returnObject|#\w+\.\w*(?:author|owner|writer|user|member)|(?:principal|authentication)\.\w+\s*==|==\s*(?:principal|authentication)|@\w+\.\w*(?:owner|author|writer|isMine|check|can)\w*\s*\(', e): return f['line']
    return None


OWNER_NAME = re.compile(r'(?i)(?:is|check|verify|ensure|require|assert|validate|confirm|has)\w*(?:owner|author|writer|ownership|mine|permission|access|creator)\w*|(?:owner|author|writer)(?:only|guard|check|permission)\w*|IsOwner\w*|Is\w*Author\w*')


def _cl(f, off):
    """(cat_backend_a 고침) code 안 줄 → 파일 줄. Java·TS 메서드 code는 어노테이션부터 시작한다."""
    if f['lang'] in ('java', 'ts') and f.get('annos') and (f.get('code') or '').startswith(f['annos']):
        return f['line'] - f['annos'].count('\n') + off - 1
    return f['line'] + off - 1


def analyze(repo, ep):
    """끝점 하나: 따라간 함수 목록, 본인 확인 근거, 따라간 깊이"""
    hits, seen, collected = [], set(), []
    work = [(h, set(), set(), 0) for h in ep['handlers']]
    while work and len(collected) < 60:
        f, tp, tc, dep = work.pop(0)
        key = (f['file'], f.get('cls'), f['name'], f['line'], frozenset(tp), frozenset(tc))
        if key in seen: continue
        seen.add(key)
        tv, cv = taint_vars(f, tp, tc)
        collected.append((f, tv))
        for nm, fn in (('P1', lambda: find_p1(f, tv, cv)), ('P2', lambda: find_p2(f, tv, repo, cv)), ('P4', lambda: find_p4(f))):
            ln = fn()
            if ln: hits.append(f'{nm}@{f["file"]}:{_cl(f, ln) if nm != "P4" else ln}')
        if dep >= 4: continue
        for recv, name, this, args, cline in calls_of(f):
            targs = [i for i, a in enumerate(args) if is_tainted(a, tv, cv)]
            cargs = [i for i, a in enumerate(args) if i not in targs and (mentions(a, cv) or (mentions(a, tv) and classify(a, tv, cv) == 'carrier'))]
            for g in repo.resolve_call(f, recv, name, this):
                for i, j in param_compares(g):
                    if i < len(args) and j < len(args) and ((is_tainted(args[i], tv, cv) and ownerish(args[j], tv)) or (is_tainted(args[j], tv, cv) and ownerish(args[i], tv))):
                        hits.append(f'P1@{f["file"]}:{_cl(f, cline or 1)}')
                gp = [p[2] for p in g['params']] if g['lang'] != 'py' else [p[2] for p in g['params'] if p[2] not in ('self', 'cls')]
                tp2 = {gp[i] for i in targs if i < len(gp)}
                tc2 = {gp[i] for i in cargs if i < len(gp)}
                if g['lang'] == 'py':
                    for a in args:
                        if '=' in a:
                            k, v = a.split('=', 1)
                            if k in gp and is_tainted(v, tv, cv): tp2.add(k)
                work.append((g, tp2, tc2, dep + 1))
    for g, tag in ep.get('guards', []):
        tv, cv = taint_vars(g, set())
        if find_p1(g, tv | {'obj.user'}, cv) or find_p2(g, tv, repo, cv) or (g['lang'] == 'py' and re.search(r'obj\.\w*(?:owner|user|author|writer|member|creator)\w*\s*(?:==|!=|is)', g['code'])):
            hits.append(f'P3@{g["file"]}:{g["line"]}')
    for name in ep.get('guard_names', []):
        if OWNER_NAME.search(name): hits.append(f'P3(이름만)@{name}')
    return hits, collected


def entity_of(repo, collected):
    """다루는 엔티티와 작성자 칸 여부: 'yes'/'no'/None"""
    ents = set()
    for f, tv in collected:
        if f['lang'] == 'java':
            for an, t, n in f['params']: pass
            for cls in repo.classes.get(f.get('cls') or '', []):
                for fld, t in cls['fields'].items():
                    bt = repo.base_type(t)
                    if bt in repo.repo_entity: ents.add(repo.repo_entity[bt])
            if f.get('cls') in repo.repo_entity: ents.add(repo.repo_entity[f['cls']])
        elif f['lang'] == 'ts':
            for mo in re.finditer(r'\bprisma\s*\.\s*(\w+)\s*\.\s*(?:update|delete|updateMany|deleteMany|upsert|findUnique|findFirst)', f['code']): ents.add(mo.group(1)[0].upper() + mo.group(1)[1:])
            for mo in re.finditer(r'Repository\s*<\s*(\w+)\s*>', f['code']): ents.add(mo.group(1))
            for mo in re.finditer(r'\b([A-Z]\w*)\s*\.\s*(?:findByIdAndUpdate|findByIdAndDelete|findOneAndUpdate|findOneAndDelete|findById|updateOne|deleteOne|findOne)\s*\(', f['code']): ents.add(mo.group(1))
            for cls in repo.classes.get(f.get('cls') or '', []):
                for fld, t in cls['fields'].items():
                    mo = re.search(r'Repository\s*<\s*(\w+)', t)
                    if mo: ents.add(mo.group(1))
                for mo in re.finditer(r'@InjectRepository\s*\(\s*(\w+)', cls.get('code', '') or f['code']): ents.add(mo.group(1))
        elif f['lang'] == 'py':
            for mo in re.finditer(r'\b([A-Z]\w*)\s*\.\s*objects\b|get_object_or_404\s*\(\s*([A-Z]\w*)|\bmodel\s*=\s*([A-Z]\w*)|\bqueryset\s*=\s*([A-Z]\w*)|db\.query\(\s*(?:models\.)?([A-Z]\w*)|session\.(?:get|query)\(\s*(?:models\.)?([A-Z]\w*)', f['code']):
                ents.add(next(g for g in mo.groups() if g))
            for cls in repo.classes.get(f.get('cls') or '', []):
                for k, v in cls.get('assigns', {}).items():
                    mo = re.search(r'\b([A-Z]\w*)\s*\.\s*objects|^([A-Z]\w*)$', v.strip())
                    if mo and k in ('queryset', 'Meta.model', 'model'): ents.add(mo.group(1) or mo.group(2))
                    mo = re.search(r'\b([A-Z]\w*)Serializer$', v.strip())
                    if mo and k == 'serializer_class':
                        for sc in repo.classes.get(v.strip(), []):
                            mm = re.search(r'([A-Z]\w*)', sc.get('assigns', {}).get('Meta.model', ''))
                            if mm: ents.add(mm.group(1))
    verdict = None
    for e in ents:
        txt = ''
        for cls in repo.classes.get(e, []): txt += cls.get('code', '') or ''
        for cls in repo.classes.get(e, []):
            if cls['lang'] == 'java':
                lang_txt = repo.files.get(cls['file'], ('', '', ''))[1]
                txt += lang_txt[cls['start']:cls['end']]
            elif cls['lang'] == 'ts':
                txt += repo.files.get(cls['file'], ('', '', ''))[1][cls['start']:cls['end']]
        for path, (lang, code, _) in repo.files.items():
            if lang == 'prisma':
                mo = re.search(r'model\s+' + re.escape(e) + r'\s*\{(.*?)\n\}', code, re.S | re.I)
                if mo: txt += mo.group(1)
        if not txt: continue
        if re.search(r'(?i)@(?:ManyToOne|OneToOne)[^;]*\b(?:User|Member|Account|Users|Members|Company|Team|Store|Customer|Seller|Owner|Author|Writer)\w*\b|\b(?:ForeignKey|OneToOneField)\s*\(\s*(?:settings\.AUTH_USER_MODEL|get_user_model\(\)|[\'"]?\w*\.?(?:User|Member|Account|Company|Team|Store)\w*[\'"]?)'
                     r'|\b(?:author|owner|writer|creator|user|member|seller|host|company|team|createdBy|created_by)\w*\s*[:=]|ForeignKey\(\s*[\'"](?:users?|members?|accounts?|companies|teams?)\.id|relationship\(\s*[\'"](?:User|Member|Account|Company)|\bref\s*:\s*[\'"](?:User|Member|Account|Company)[\'"]'
                     r'|\b(?:author|owner|writer|creator|user|member|seller|company)_?[Ii]d\b', txt):
            verdict = 'yes'
            break
        verdict = verdict or 'no'
    return verdict, sorted(ents)


PATH_VAR = re.compile(r'\{[^}]+\}|:\w+|<[^>]+>|\[[^\]]+\]')
MOD_WORD = re.compile(r'(?i)update|edit|modify|change|delete|remove|cancel|withdraw|destroy|patch|archive|restore|toggle|close|reopen|approve|reject|complete|move|rename|reset'
                      r'|read|like|unlike|finish|confirm|accept|join|leave|mark|pin|follow|block|upsert|register|submit|assign|transfer|status|state|end|start|stop|enable|disable|activate|deactivate|publish|hide|recover')


def routes(repo, keep_all=False):
    eps = []
    # Spring
    for cname, cl in repo.classes.items():
        for cls in cl:
            if cls['lang'] == 'java' and re.search(r'@(?:Rest)?Controller\b', cls['annos']):
                mo = re.search(r'@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*"([^"]*)"', cls['annos'])
                prefix = mo.group(1) if mo else ''
                for mname, fl in cls['methods'].items():
                    for f in fl:
                        am = re.search(r'@(Get|Post|Put|Patch|Delete)Mapping\b(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*"([^"]*)")?|@RequestMapping\s*\(([^)]*)\)', f['annos'])
                        if not am: continue
                        verb = (am.group(1) or '').upper()
                        path = am.group(2) or ''
                        if am.group(3):
                            vm = re.search(r'RequestMethod\.(\w+)', am.group(3)); verb = vm.group(1) if vm else 'ANY'
                            pm = re.search(r'"([^"]*)"', am.group(3)); path = pm.group(1) if pm else ''
                        eps.append(dict(file=f['file'], line=f['line'], kind='spring', verb=verb, path=prefix + path, name=mname, handlers=[f], guards=[], guard_names=[]))
            if cls['lang'] == 'ts' and re.search(r'@(?:Json)?Controller\s*\(', cls['annos']):
                mo = re.search(r'@(?:Json)?Controller\s*\(\s*(?:\{\s*path\s*:\s*)?[\'"`]([^\'"`]*)', cls['annos'])
                prefix = mo.group(1) if mo else ''
                cg = re.findall(r'@UseGuards\s*\(([^)]*)\)', cls['annos'])
                for mname, fl in cls['methods'].items():
                    for f in fl:
                        am = re.search(r'@(Get|Post|Put|Patch|Delete|All)\s*\(\s*(?:[\'"`]([^\'"`]*)[\'"`])?', f['annos'])
                        if not am: continue
                        gnames = [g.strip() for x in cg + re.findall(r'@UseGuards\s*\(([^)]*)\)', f['annos']) for g in x.split(',') if g.strip()]
                        guards = []
                        for g in gnames:
                            gb = re.sub(r'\(.*', '', g).replace('new ', '').strip()
                            guards += [(x, 'guard') for x in repo.class_methods(gb, 'canActivate')]
                        eps.append(dict(file=f['file'], line=f['line'], kind='nest', verb=am.group(1).upper(), path=prefix + '/' + (am.group(2) or ''), name=mname, handlers=[f], guards=guards, guard_names=gnames))
    # Express / Koa / Fastify / Next
    for path, (lang, code, masked) in repo.files.items():
        if lang != 'ts': continue
        if FRONT.search(path) and not re.search(r'(^|/)(server|api|backend)(/|$)', path): continue
        if re.search(r'\bfrom\s+[\'"]axios[\'"]|require\(\s*[\'"]axios[\'"]', code) and not re.search(r'express|fastify|koa|Router\s*\(', code): continue
        routers = set(re.findall(r'(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:express\s*\.\s*Router|Router|express|fastify|Fastify|new\s+(?:Koa)?Router|new\s+Hono|Hono)\s*\(', code))
        routers |= set(re.findall(r'(?:async\s+)?(?:function\s*\w*\s*)?\(\s*(app|router|fastify|server|instance|api|r)\b\s*(?::\s*[\w.<>]+)?\s*[,)]', code))
        routers |= {'app', 'router', 'fastify', 'server', 'api', 'routes', 'route'} if re.search(r'express|fastify|koa|hono|Router\s*\(', code) else set()
        for mo in re.finditer(r'(\)|\b[A-Za-z_$][\w$]*)\s*\.\s*(get|post|put|patch|delete|del|all)\s*(?:<[^>()]*>)?\s*\(', masked):
            recv, verb = mo.group(1), mo.group(2).upper().replace('DEL', 'DELETE').replace('DELETEETE', 'DELETE')
            if recv != ')' and recv not in routers and not re.match(r'(?i).*router$|.*routes?$', recv): continue
            if recv == ')':
                back = masked[max(0, mo.start() - 400):mo.start()]
                if '.route' not in back and not re.search(r'\b(?:router|app|r)\b', back): continue
            p = mo.end() - 1
            q = match(masked, p, '(', ')')
            args = split_top(code[p + 1:q], masked[p + 1:q])
            if not args: continue
            rpath = args[0][0] if re.match(r'^[\'"`]', args[0][0]) else ''
            if recv == ')':
                rm = re.search(r'\.route\s*\(\s*([\'"`][^\'"`]*[\'"`])\s*\)[^;]*$', code[max(0, mo.start() - 400):mo.start()], re.S)
                rpath = rm.group(1) if rm else ''
            elif not rpath:
                continue
            hs, guard_fs, gnames = [], [], []
            rest = args if recv == ')' else args[1:]
            for i, (a, am) in enumerate(rest):
                is_last = i == len(rest) - 1
                inline = re.search(r'=>\s*\{|function\s*[\w$]*\s*\(', a)
                fns = []
                if inline:
                    off = code.find(a, p)
                    if off >= 0:
                        bm = re.search(r'=>\s*\{|function\s*[\w$]*\s*\([^)]*\)\s*\{', masked[off:off + len(a)])
                        if bm:
                            bb = off + bm.end() - 1
                            be = match(masked, bb, '{', '}')
                            prm = re.search(r'\(([^()]*)\)\s*(?::[^=]+)?=>|function\s*[\w$]*\s*\(([^)]*)\)', a)
                            fns.append(dict(lang='ts', file=path, cls=None, name=f'<inline:{line_of(masked, off)}>', params=Repo.ts_params((prm.group(1) or prm.group(2) or '') if prm else '', (prm.group(1) or prm.group(2) or '') if prm else ''),
                                            code=code[off:be + 1], masked=masked[off:be + 1], line=line_of(masked, off), annos=''))
                else:
                    for ref in re.findall(r'(?<![\w$.\'"])([A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)?)', a):
                        parts = [x.strip() for x in ref.split('.')]
                        if parts[-1] in STOP or parts[-1] in ('async', 'await', 'req', 'res', 'next'): continue
                        dummy = dict(lang='ts', file=path, cls=None, name='<route>', params=[], code='', masked='', line=0, annos='')
                        got = repo.resolve_call(dummy, parts[0] if len(parts) > 1 else None, parts[-1], False)
                        fns += got
                        if not is_last: gnames.append(ref)
                if is_last or inline: hs += fns
                else: guard_fs += [(g, 'mw') for g in fns]
            if verb == 'GET' and not keep_all: continue
            eps.append(dict(file=path, line=line_of(masked, mo.start()), kind='express', verb=verb, path=rpath.strip('\'"`'), name='', handlers=hs, guards=guard_fs, guard_names=gnames))
        for mo in re.finditer(r'\.route\s*\(\s*\{', masked):
            b = mo.end() - 1
            e = match(masked, b, '{', '}')
            obj = code[b:e + 1]
            vm = re.findall(r'(PUT|PATCH|DELETE|POST)', re.search(r'method\s*:\s*([^\n,]+(?:\[[^\]]*\])?)', obj).group(1)) if re.search(r'method\s*:', obj) else []
            um = re.search(r'url\s*:\s*[\'"`]([^\'"`]*)', obj)
            hm = re.search(r'handler\s*:\s*([\w$.]+)', obj)
            if vm:
                dummy = dict(lang='ts', file=path, cls=None, name='<route>', params=[], code='', masked='', line=0, annos='')
                hs = []
                if hm:
                    parts = hm.group(1).split('.')
                    hs = repo.resolve_call(dummy, parts[0] if len(parts) > 1 else None, parts[-1], False)
                eps.append(dict(file=path, line=line_of(masked, mo.start()), kind='fastify-route', verb='/'.join(vm), path=um.group(1) if um else '', name='', handlers=hs, guards=[], guard_names=[]))
        if re.search(r'(^|/)app/.*route\.(ts|js)$', path) or re.search(r'(^|/)pages/api/', path):
            for mo in re.finditer(r'export\s+(?:async\s+)?function\s+(PUT|PATCH|DELETE|POST)\s*\(|export\s+const\s+(PUT|PATCH|DELETE|POST)\s*=', masked):
                verb = mo.group(1) or mo.group(2)
                fl = repo.file_funcs[path].get(verb, [])
                eps.append(dict(file=path, line=line_of(masked, mo.start()), kind='next', verb=verb, path=path, name=verb, handlers=fl, guards=[], guard_names=[]))
            for mo in re.finditer(r'req\s*\.\s*method\s*===?\s*[\'"](PUT|PATCH|DELETE|POST)[\'"]', code):
                eps.append(dict(file=path, line=line_of(code, mo.start()), kind='next-pages', verb=mo.group(1), path=path, name='', handlers=[f for fl in repo.file_funcs[path].values() for f in fl][:3], guards=[], guard_names=[]))
    # Python
    for name, fl in list(repo.funcs.items()):
        for f in fl:
            if f['lang'] != 'py': continue
            dm_ = re.search(r'@[\w.]+\.(get|post|put|patch|delete|api_route|route)\s*\(([^\n]*)', f['annos'])
            if dm_:
                verb = dm_.group(1).upper()
                if verb in ('ROUTE', 'API_ROUTE'):
                    ms = re.findall(r'(PUT|PATCH|DELETE|POST)', dm_.group(2).upper())
                    if not ms: continue
                    verb = '/'.join(sorted(set(ms)))
                pm = re.search(r'[\'"]([^\'"]*)[\'"]', dm_.group(2))
                eps.append(dict(file=f['file'], line=f['line'], kind='py-deco', verb=verb, path=pm.group(1) if pm else '', name=name, handlers=[f], guards=[], guard_names=[]))
                continue
            av = re.search(r'@api_view\s*\(\s*\[([^\]]*)\]|@require_http_methods\s*\(\s*\[([^\]]*)\]', f['annos'])
            if av:
                ms = re.findall(r'(PUT|PATCH|DELETE|POST)', (av.group(1) or av.group(2) or '').upper())
                if ms: eps.append(dict(file=f['file'], line=f['line'], kind='py-fview', verb='/'.join(sorted(set(ms))), path='', name=name, handlers=[f], guards=[], guard_names=[]))
                continue
            if f['cls'] is None and re.search(r'request\.method\s*==\s*[\'"](PUT|PATCH|DELETE)[\'"]', f['code']):
                ms = re.findall(r'request\.method\s*==\s*[\'"](PUT|PATCH|DELETE)[\'"]', f['code'])
                eps.append(dict(file=f['file'], line=f['line'], kind='py-fview', verb='/'.join(sorted(set(ms))), path='', name=name, handlers=[f], guards=[], guard_names=[]))
    for cname, cl in repo.classes.items():
        for cls in cl:
            if cls['lang'] != 'py': continue
            hdr = cls['header']
            perm = cls.get('assigns', {}).get('permission_classes', '')
            pnames = re.findall(r'\b([A-Za-z_]\w*)', perm)
            guards = [(g, 'perm') for pn in pnames for g in repo.class_methods(pn, 'has_object_permission') + repo.class_methods(pn, 'has_permission')]
            implicit = re.search(r'ModelViewSet|UpdateModelMixin|DestroyModelMixin|UpdateAPIView|DestroyAPIView|RetrieveUpdateDestroyAPIView|RetrieveUpdateAPIView|RetrieveDestroyAPIView|UpdateView|DeleteView', hdr)
            extra = [f for mn in ('get_queryset', 'get_object', 'perform_update', 'perform_destroy') for f in cls['methods'].get(mn, [])]
            if implicit:
                hs = [f for mn in ('update', 'partial_update', 'destroy') for f in cls['methods'].get(mn, [])] + extra
                if not hs: hs = [dict(lang='py', file=cls['file'], cls=cname, name='<implicit>', params=[], code=cls['code'], masked=cls['code'], line=cls['line'], annos='', node=None)]
                eps.append(dict(file=cls['file'], line=cls['line'], kind='drf-generic', verb='PUT/PATCH/DELETE', path='', name=cname, handlers=hs, guards=guards, guard_names=pnames))
            elif re.search(r'APIView|View\b|ViewSet', hdr):
                for mn in ('put', 'patch', 'delete', 'update', 'partial_update', 'destroy'):
                    for f in cls['methods'].get(mn, []):
                        eps.append(dict(file=f['file'], line=f['line'], kind='drf-view', verb=mn.upper(), path='', name=cname + '.' + mn, handlers=[f] + extra, guards=guards, guard_names=pnames))
            for mn, fl in cls['methods'].items():
                for f in fl:
                    am = re.search(r'@action\s*\(([^)]*)\)', f['annos'])
                    if am and re.search(r'detail\s*=\s*True', am.group(1)):
                        ms = re.findall(r'(put|patch|delete|post)', am.group(1).lower())
                        if ms: eps.append(dict(file=f['file'], line=f['line'], kind='drf-action', verb='/'.join(sorted(set(x.upper() for x in ms))), path=mn, name=cname + '.' + mn, handlers=[f] + extra, guards=guards, guard_names=pnames))
    if keep_all:
        return eps
    out = []
    for e in eps:
        v = e['verb']
        if v in ('GET', 'ANY', 'ALL'): continue
        if 'POST' in v and not any(x in v for x in ('PUT', 'PATCH', 'DELETE')):
            label = (e['path'] or '') + ' ' + (e['name'] or '') + ' ' + ' '.join(h['name'] for h in e['handlers'])
            if not (PATH_VAR.search(e['path'] or '') or MOD_WORD.search(label)): continue
            e['post_modify'] = True
        out.append(e)
    return out


def main():
    pm = json.load(open(sys.argv[1]))
    outp, ids = sys.argv[2], sys.argv[3:]
    res = []
    for rid in ids:
        repo = Repo(rid, pm[rid])
        eps = routes(repo)
        for i, e in enumerate(eps):
            hits, collected = analyze(repo, e)
            ent, ents = entity_of(repo, collected)
            path = e['path'] or ''
            self_only = not PATH_VAR.search(path) and e['kind'] not in ('drf-generic', 'drf-view', 'drf-action', 'py-fview')
            guard_txt = ' '.join(e.get('guard_names', [])) + ' ' + ' '.join(h.get('annos', '') or '' for h in e['handlers'][:1])
            for cl in repo.classes.values():
                for cls in cl:
                    if e['handlers'] and cls['name'] == e['handlers'][0].get('cls') and cls['file'] == e['file']: guard_txt += ' ' + (cls.get('annos') or '')
            admin_only = bool(re.search(r'(?i)(^|/)admin(/|$)', path)) or bool(re.search(r'(?i)hasRole\(\s*[\'"](?:ROLE_)?ADMIN|hasAuthority\(\s*[\'"](?:ROLE_)?ADMIN|@Secured\s*\(\s*\{?\s*"ROLE_ADMIN|@RolesAllowed|@Roles\s*\(\s*[\'"\w.]*admin|\bAdmin\w*Guard\b|\b(?:isAdmin|adminOnly|requireAdmin|checkAdmin|verifyAdmin|IsAdminUser)\b', guard_txt))
            strong = [h for h in hits if not h.startswith('P3(이름만)')]
            unresolved = [c for f, _ in collected for c in []]
            decision = 'yes' if strong else ('weak' if hits else 'no')
            res.append(dict(id=f'{rid}-V{i + 1:03d}', repo=rid, file=e['file'], line=e['line'], kind=e['kind'], verb=e['verb'], path=path[:120], name=e.get('name', ''),
                            handlers=len(e['handlers']), followed=len(collected), hits=hits[:6], rule_check=decision, owned_rule=('admin' if admin_only else 'self' if self_only else (ent or 'unclear')), entities=ents[:4],
                            post_modify=e.get('post_modify', False)))
        print(rid, 'files', len(repo.files), 'endpoints', len(eps), 'yes', sum(1 for r in res if r['repo'] == rid and r['rule_check'] == 'yes'), 'unresolved-name-calls', repo.unresolved, file=sys.stderr)
    json.dump(res, open(outp, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    sys.setrecursionlimit(10000)
    main()
