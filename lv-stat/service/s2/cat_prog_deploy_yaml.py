"""작은 YAML 부분 파서(버림용 스파이크, 2026-11-26). 쓴 파서 이름: PARSER.

설계 9.8은 판을 고정한 YAML 라이브러리(safe_load 꼴)를 쓰라고 했지만, 이 기계의 python3 -I에는 PyYAML이 없다.
GitHub Actions 워크플로가 쓰는 부분(블록 매핑·블록 시퀀스·블록 스칼라 |·>·흐름 [..]·{..}·따옴표 스칼라·주석)만 읽고
줄 번호를 남긴다. 별칭(&·*)·여러 문서(---)·태그는 풀지 않는다. 못 읽으면 YamlError를 낸다(몰래 정규식으로 바꾸지 않음).
"""
import re

PARSER = 'mini-yaml@spike1'
KEY = re.compile(r'''^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s#'"\[\]{},&*!|>%@`][^#]*?|\$\{\{[^}]*\}\})\s*:(?=\s|$)''')


class YamlError(Exception):
    pass


def _unq(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
        return s[1:-1]
    return s


def strip_plain_comment(s):
    """따옴표로 시작하지 않는 값: ' #' 또는 맨 앞 '#'부터 주석."""
    for i, ch in enumerate(s):
        if ch == '#' and (i == 0 or s[i - 1] in ' \t'):
            return s[:i].rstrip()
    return s.rstrip()


class _P:
    def __init__(self, text):
        self.raw = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        self.n = len(self.raw)

    def ind(self, i):
        line = self.raw[i]
        return len(line) - len(line.lstrip(' '))

    def blank(self, i):
        s = self.raw[i].strip()
        return s == '' or s.startswith('#') or s in ('---', '...')

    def nxt(self, i):
        while i < self.n and self.blank(i):
            i += 1
        return i

    @staticmethod
    def is_seq(s):
        return s == '-' or s.startswith('- ') or s.startswith('-\t')

    def block(self, j):
        s = self.raw[j].strip()
        ind = self.ind(j)
        if self.is_seq(s):
            return self.seq(j, ind)
        if KEY.match(s):
            return self.mapping(j, ind)
        return self.plain_block(j, ind)

    def plain_block(self, j, ind):
        lines, k = [], j
        while k < self.n and (self.blank(k) or self.ind(k) >= ind):
            if not self.blank(k):
                if self.ind(k) == ind and k != j and (KEY.match(self.raw[k].strip()) or self.is_seq(self.raw[k].strip())):
                    break
                lines.append((k + 1, self.raw[k]))
            k += 1
        txt = ' '.join(strip_plain_comment(t.strip()) for _, t in lines)
        return dict(t='str', v=txt, line=j + 1, end=lines[-1][0] if lines else j + 1, lines=lines), k

    def mapping(self, j, ind, first=None):
        items, start = [], j
        if first is not None:
            key, rest = first
            val, j = self.value(j, ind, rest)
            items.append((key, start + 1, val))
        while True:
            j = self.nxt(j)
            if j >= self.n or self.ind(j) != ind:
                break
            s = self.raw[j].strip()
            if self.is_seq(s):
                break
            m = KEY.match(s)
            if not m:
                raise YamlError(f'줄 {j + 1}: 키를 못 읽음')
            key = _unq(m.group(1))
            rest = s[m.end():].strip()
            kl = j
            val, j = self.value(j, ind, rest)
            items.append((key, kl + 1, val))
        return dict(t='map', items=items, line=start + 1), j

    def value(self, j, ind, rest):
        if rest.startswith(('"', "'")):
            return self.quoted(j, ind, rest)
        r = strip_plain_comment(rest)
        if r.startswith(('&', '!')):            # 앵커·태그는 떼고 읽는다
            r = re.sub(r'^[&!]\S*\s*', '', r)
        if r == '':
            k = self.nxt(j + 1)
            if k < self.n and self.ind(k) > ind:
                return self.block(k)
            if k < self.n and self.ind(k) == ind and self.is_seq(self.raw[k].strip()):
                return self.seq(k, ind)
            return dict(t='null', line=j + 1, end=j + 1), j + 1
        if re.fullmatch(r'[|>][-+0-9]*', r):
            k, lines = j + 1, []
            while k < self.n and (self.raw[k].strip() == '' or self.ind(k) > ind):
                lines.append((k + 1, self.raw[k]))
                k += 1
            while lines and lines[-1][1].strip() == '':
                lines.pop()
            txt = '\n'.join(t for _, t in lines)
            return dict(t='str', v=txt, line=j + 1, end=lines[-1][0] if lines else j + 1, lines=lines, block=True), k
        if r[0] in '[{':
            return self.flow(j, r)
        lines, k = [(j + 1, r)], j + 1
        while k < self.n and not self.blank(k) and self.ind(k) > ind:
            lines.append((k + 1, strip_plain_comment(self.raw[k].strip())))
            k += 1
        return dict(t='str', v=' '.join(t for _, t in lines), line=j + 1, end=lines[-1][0], lines=lines), k

    def quoted(self, j, ind, rest):
        q = rest[0]
        buf, k, line = rest, j, j
        while True:
            body = buf[1:]
            close = None
            i = 0
            while i < len(body):
                ch = body[i]
                if q == '"' and ch == '\\':
                    i += 2
                    continue
                if ch == q:
                    if q == "'" and i + 1 < len(body) and body[i + 1] == "'":
                        i += 2
                        continue
                    close = i
                    break
                i += 1
            if close is not None:
                return dict(t='str', v=body[:close], line=j + 1, end=line + 1, lines=[(j + 1, body[:close])]), line + 1
            line += 1
            if line >= self.n:
                raise YamlError(f'줄 {j + 1}: 따옴표가 안 닫힘')
            buf = buf + ' ' + self.raw[line].strip()

    def flow(self, j, r):
        depth, buf, k = 0, r, j
        while True:
            depth = 0
            q = None
            for ch in buf:
                if q:
                    if ch == q:
                        q = None
                elif ch in '"\'':
                    q = ch
                elif ch in '[{':
                    depth += 1
                elif ch in ']}':
                    depth -= 1
            if depth <= 0:
                break
            k += 1
            if k >= self.n:
                raise YamlError(f'줄 {j + 1}: 괄호가 안 닫힘')
            buf += ' ' + strip_plain_comment(self.raw[k].strip())
        inner = buf.strip()[1:-1]
        parts = [_unq(x) for x in re.split(r',(?![^\[{]*[\]}])', inner) if x.strip()]
        if buf.strip().startswith('['):
            return dict(t='seq', items=[dict(t='str', v=p, line=j + 1, end=k + 1, lines=[(j + 1, p)]) for p in parts], line=j + 1, flow=True), k + 1
        items = []
        for p in parts:
            a, _, b = p.partition(':')
            items.append((_unq(a), j + 1, dict(t='str', v=_unq(b), line=j + 1, end=k + 1, lines=[(j + 1, b)])))
        return dict(t='map', items=items, line=j + 1, flow=True), k + 1

    def seq(self, j, ind):
        items, start = [], j
        while True:
            j = self.nxt(j)
            if j >= self.n or self.ind(j) != ind:
                break
            s = self.raw[j].strip()
            if not self.is_seq(s):
                break
            rest = s[1:].lstrip(' \t')
            col = ind + (len(s) - len(rest))
            rc = strip_plain_comment(rest) if not rest.startswith(('"', "'")) else rest
            if rc == '':
                k = self.nxt(j + 1)
                if k < self.n and self.ind(k) > ind:
                    val, j = self.block(k)
                else:
                    val, j = dict(t='null', line=j + 1, end=j + 1), j + 1
            elif self.is_seq(rest):
                raise YamlError(f'줄 {j + 1}: 한 줄 안의 겹친 시퀀스')
            else:
                m = KEY.match(rest)
                if m and not rest.startswith(('"', "'")) or (m and rest.startswith(('"', "'")) and re.match(r'''^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')\s*:(\s|$)''', rest)):
                    val, j = self.mapping(j, col, first=(_unq(m.group(1)), rest[m.end():].strip()))
                else:
                    val, j = self.value(j, ind, rest)
            items.append(val)
        return dict(t='seq', items=items, line=start + 1), j


def parse(text):
    p = _P(text)
    j = p.nxt(0)
    if j >= p.n:
        return dict(t='null', line=1, end=1)
    node, j = p.block(j)
    j = p.nxt(j)
    if j < p.n:
        raise YamlError(f'줄 {j + 1}: 읽지 못한 줄이 남음')
    return node


def get(node, key):
    if node and node.get('t') == 'map':
        for k, kl, v in node['items']:
            if k == key:
                return v
    return None


def key_line(node, key):
    if node and node.get('t') == 'map':
        for k, kl, v in node['items']:
            if k == key:
                return kl
    return None


def scalar(node):
    if node and node.get('t') == 'str':
        return node['v']
    return None


def scalar_lines(node):
    """스칼라 값의 (줄 번호, 글) 목록. 블록 스칼라는 줄마다."""
    if not node:
        return []
    if node.get('t') == 'str':
        return node.get('lines') or [(node['line'], node['v'])]
    out = []
    if node.get('t') == 'map':
        for k, kl, v in node['items']:
            out += scalar_lines(v)
    elif node.get('t') == 'seq':
        for v in node['items']:
            out += scalar_lines(v)
    return out
