"""cat_fe 보조: JS·TS(JSX) 손 렉서와 SFC(.vue·.svelte)·HTML 구역 나누기. 버림용 스파이크(2026-11-26).

설계 9.8은 JS·TS를 tree-sitter로 읽으라고 한다. 이 스파이크 환경에는 tree-sitter가 없어서
'손 렉서(주석·문자열·정규식 리터럴 가림) + 정규식'을 쓰고, 결과의 parser 칸에 그 사실을 적는다(몰래 바꾸지 않음).
- masked: 원문과 길이가 같다. 주석과 문자열·정규식 내용은 공백(줄바꿈은 그대로), 따옴표·템플릿 ${} 식은 남는다.
- strings: [Str(start, end, q, parts)] parts = [('lit', s, e) | ('expr', s, e)] (원문 위치)
"""
import bisect
import re

KW_REGEX = {'return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete', 'void', 'throw', 'yield', 'await', 'instanceof'}
REGEX_PREV = set('(,=:[!&|?{};+-*%~^')
_SPECIAL = re.compile(r'[/\'"`{}]')


class Str:
    __slots__ = ('start', 'end', 'q', 'parts')

    def __init__(self, start, end, q, parts):
        self.start, self.end, self.q, self.parts = start, end, q, parts


def _prev_sig(out, i, lo):
    k = i - 1
    while k >= lo and out[k] in ' \t\r\n':
        k -= 1
    if k < lo:
        return '', ''
    c = out[k]
    if c.isalnum() or c in '_$':
        j = k
        while j >= lo and (out[j].isalnum() or out[j] in '_$'):
            j -= 1
        return 'w', ''.join(out[j + 1:k + 1])
    return c, ''


def _blank(out, s, e):
    for k in range(s, e):
        if out[k] != '\n':
            out[k] = ' '


def _lex(src, i, end, out, strings, lo, stop_at_brace=False):
    depth = 0
    while i < end:
        m = _SPECIAL.search(src, i, end)
        if not m:
            return end
        i = m.start()
        c = src[i]
        if c == '/':
            n2 = src[i + 1] if i + 1 < end else ''
            if n2 == '/':
                j = src.find('\n', i, end)
                j = end if j == -1 else j
                _blank(out, i, j)
                i = j
                continue
            if n2 == '*':
                j = src.find('*/', i + 2, end)
                j = end if j == -1 else j + 2
                _blank(out, i, j)
                i = j
                continue
            p, w = _prev_sig(out, i, lo)
            if p == '' or (p in REGEX_PREV) or (p == 'w' and w in KW_REGEX):
                j, cls = i + 1, False
                ok = False
                while j < end:
                    ch = src[j]
                    if ch == '\\':
                        j += 2
                        continue
                    if ch == '\n':
                        break
                    if ch == '[':
                        cls = True
                    elif ch == ']':
                        cls = False
                    elif ch == '/' and not cls:
                        ok = True
                        break
                    j += 1
                if ok and j > i + 1:
                    _blank(out, i + 1, j)
                    i = j + 1
                    continue
            i += 1
            continue
        if c in '\'"':
            j = i + 1
            while j < end and src[j] != c and src[j] != '\n':
                j += 2 if src[j] == '\\' else 1
            if j < end and src[j] == c:
                strings.append(Str(i, j + 1, c, [('lit', i + 1, j)]))
                _blank(out, i + 1, j)
                i = j + 1
            else:                      # 줄 끝까지 안 닫힘: JSX 글(Don't 등)로 보고 넘긴다
                i += 1
            continue
        if c == '`':
            parts, j, ls = [], i + 1, i + 1
            while j < end:
                ch = src[j]
                if ch == '\\':
                    j += 2
                    continue
                if ch == '`':
                    break
                if ch == '$' and j + 1 < end and src[j + 1] == '{':
                    parts.append(('lit', ls, j))
                    _blank(out, ls, j)
                    k = _lex(src, j + 2, end, out, strings, lo, stop_at_brace=True)
                    parts.append(('expr', j + 2, k))
                    j = k + 1
                    ls = j
                    continue
                j += 1
            je = min(j, end)
            parts.append(('lit', ls, je))
            _blank(out, ls, je)
            strings.append(Str(i, je + 1, '`', parts))
            i = je + 1
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            if stop_at_brace and depth == 0:
                return i
            depth -= 1
        i += 1
    return end


class Lexed:
    """파일 하나. regions: [(kind, s, e, lang)] kind = code·markup·style"""

    def __init__(self, text, regions):
        self.text = text
        self.regions = regions
        out = list(text)
        strings = []
        for kind, s, e, lang in regions:
            if kind == 'code':
                _lex(text, s, e, out, strings, s)
            elif kind == 'markup':
                for m in re.finditer(r'<!--.*?-->', text[s:e], re.S):
                    _blank(out, s + m.start(), s + m.end())
        # 코드 구역 밖(마크업·스타일)은 masked에서 지우지 않는다. 코드 검색은 code_spans 안에서만 한다.
        self.masked = ''.join(out)
        strings.sort(key=lambda x: x.start)
        self.strings = strings
        self._sstarts = [x.start for x in strings]
        self.line_starts = [0] + [m.end() for m in re.finditer('\n', text)]

    def line(self, off):
        return bisect.bisect_right(self.line_starts, off)

    def str_at(self, off):
        """off에서 시작하는 문자열(없으면 None)"""
        k = bisect.bisect_left(self._sstarts, off)
        if k < len(self.strings) and self.strings[k].start == off:
            return self.strings[k]
        return None

    def strings_in(self, s, e):
        k = bisect.bisect_left(self._sstarts, s)
        res = []
        while k < len(self.strings) and self.strings[k].start < e:
            if self.strings[k].end <= e:
                res.append(self.strings[k])
            k += 1
        return res

    def lit(self, st):
        """문자열 내용(템플릿은 ${}를 {x}로)"""
        out = []
        for kind, s, e in st.parts:
            out.append(self.text[s:e] if kind == 'lit' else '{x}')
        return ''.join(out)

    def code_spans(self):
        return [(s, e) for kind, s, e, lang in self.regions if kind == 'code']


def match_close(masked, i, end=None, open_='(', close=')'):
    """masked[i] == open_ 일 때 맞는 닫는 괄호 위치(없으면 -1). 문자열은 가려져 있다."""
    end = len(masked) if end is None else end
    pairs = {'(': ')', '[': ']', '{': '}'}
    stack = []
    j = i
    while j < end:
        ch = masked[j]
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in ')]}':
            if not stack or stack[-1] != ch:
                return -1
            stack.pop()
            if not stack:
                return j
        j += 1
    return -1


def split_args(masked, lp, rp):
    """괄호 (lp, rp) 안의 최상위 인자 [(s, e)]"""
    args, depth, s = [], 0, lp + 1
    for j in range(lp + 1, rp):
        ch = masked[j]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ',' and depth == 0:
            args.append((s, j))
            s = j + 1
    if masked[s:rp].strip():
        args.append((s, rp))
    out = []
    for a, b in args:
        while a < b and masked[a] in ' \t\r\n':
            a += 1
        while b > a and masked[b - 1] in ' \t\r\n':
            b -= 1
        out.append((a, b))
    return out


SFC_BLOCK = re.compile(r'<(script|style)(\s[^>]*)?>', re.I)


def regions_for(path, text):
    """파일 종류별 구역. .vue·.svelte·.html은 script/style/나머지(markup), JS·TS는 전부 code."""
    low = path.lower()
    n = len(text)
    if low.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
        lang = 'ts' if low.endswith(('.ts', '.tsx')) else 'js'
        return [('code', 0, n, lang)]
    if low.endswith(('.css', '.scss', '.sass', '.less', '.styl')):
        return [('style', 0, n, low.rsplit('.', 1)[-1])]
    regions, pos = [], 0
    for m in SFC_BLOCK.finditer(text):
        if m.start() < pos:
            continue
        tag = m.group(1).lower()
        attrs = m.group(2) or ''
        close = re.compile(r'</' + tag + r'\s*>', re.I).search(text, m.end())
        ce = close.start() if close else n
        if m.start() > pos:
            regions.append(('markup', pos, m.start(), 'html'))
        regions.append(('markup', m.start(), m.end(), 'html'))
        if tag == 'script':
            if re.search(r'\bsrc\s*=', attrs) or re.search(r'type\s*=\s*["\']?(text/(template|x-template|html)|application/(ld\+)?json|importmap)', attrs, re.I):
                regions.append(('markup', m.end(), ce, 'html'))
            else:
                lm = re.search(r'lang\s*=\s*["\']?(ts|typescript|tsx)', attrs, re.I)
                regions.append(('code', m.end(), ce, 'ts' if lm else 'js'))
        else:
            lm = re.search(r'lang\s*=\s*["\']?(scss|sass|less|stylus|styl|postcss)', attrs, re.I)
            regions.append(('style', m.end(), ce, (lm.group(1).lower() if lm else 'css')))
        pos = ce
    if pos < n:
        regions.append(('markup', pos, n, 'html'))
    return regions
