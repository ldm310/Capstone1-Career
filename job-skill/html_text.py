"""
글 공고(사람인 본문 HTML) -> LLM 입력 글. 화면에 보이는 글만 쓰고 구조를 살린다.

  - 숨긴 글(display:none, visibility:hidden, font-size:0, height:0 + overflow:hidden)은 뺀다(이미지형 공고의 검색용 글 등).
  - 줄: 블록 태그(div, p, li, tr …)와 <br> 에서 줄을 바꾼다. 목록 항목은 '• '를 붙인다.
  - 표: OCR 쪽 표 정리(table_layout)와 같은 모양으로 낸다.
      · 머리말 줄이 있는 표(짧은 칸 2개 이상 + 아래 행들): 행마다 칸 순서대로 '■ 머리말' + 그 칸 글.
        왼쪽 칸이 위아래로 합쳐져(rowspan) 칸 수가 모자란 행은 오른쪽 칸들에 맞춘다.
      · 왼쪽 머리말 표(짧은 칸 | 내용): '■ 머리말' + 내용.
      · 그 밖(레이아웃용 표 등): 한 줄짜리 칸만 있으면 ' | '로 잇고, 아니면 칸을 차례로.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

VOID = {"img", "br", "hr", "input", "meta", "link", "area", "col", "source", "wbr", "base", "param", "embed", "track"}
BLOCK = {"div", "p", "li", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
         "header", "footer", "blockquote", "pre", "table", "tr", "tbody", "thead", "tfoot", "center", "form", "nav"}
HIDE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(px)?\s*(;|$)", re.I)
BODY = re.compile(r'<div class="user_content">(.*?)<script', re.S)
BULLET = re.compile(r"^\s*([-–—·•*▶▷※□■○●◆◇√✓ㆍ]|\d{1,2}[.)])")
HEAD_MAX = 20


class Node:
    __slots__ = ("tag", "attrs", "kids", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.kids, self.parent = tag, dict(attrs or []), [], parent


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.kids.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:  # 닫는 태그가 어긋난 HTML 도 견딘다
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, d):
        self.cur.kids.append(d)


def hidden(n: Node) -> bool:
    if n.tag in ("script", "style", "head", "title", "noscript"):
        return True
    st = (n.attrs.get("style") or "").lower()
    if HIDE.search(st):
        return True
    return bool(re.search(r"height\s*:\s*0(px)?\s*(;|$)", st)) and "overflow" in st and "hidden" in st


def lines_of(n) -> list[str]:
    """노드 -> 줄 목록(빈 줄 없음)."""
    out, buf = [], []

    def flush():
        s = re.sub(r"\s+", " ", "".join(buf)).strip()
        if s:
            out.append(s)
        buf.clear()

    def walk(x):
        if isinstance(x, str):
            buf.append(x)
            return
        if hidden(x):
            return
        if x.tag == "br":
            flush()
            return
        if x.tag == "table":
            flush()
            out.extend(table_lines(x))
            return
        if x.tag in BLOCK:
            flush()
        start = len(out)
        for k in x.kids:
            walk(k)
        if x.tag in BLOCK:
            flush()
        if x.tag == "li" and len(out) > start and not BULLET.match(out[start]):
            out[start] = "• " + out[start]

    walk(n)
    flush()
    return out


def rows_of(table: Node) -> list[list[list[str]]]:
    """표 -> 행 -> 칸 -> 줄. 안쪽 표의 행은 그 표가 맡는다."""
    rows = []

    def walk(x):
        for k in x.kids:
            if isinstance(k, Node) and not hidden(k):
                if k.tag == "tr":
                    rows.append([lines_of(c) for c in k.kids if isinstance(c, Node) and c.tag in ("td", "th") and not hidden(c)])
                elif k.tag != "table":
                    walk(k)

    walk(table)
    return [r for r in rows if any(r)]


def short(cell: list[str]) -> bool:
    return len(cell) == 1 and len(re.sub(r"\s", "", cell[0])) <= HEAD_MAX and not BULLET.match(cell[0])


def table_lines(table: Node) -> list[str]:
    rows = rows_of(table)
    out = []
    i = 0
    while i < len(rows):
        r = rows[i]
        cells = [c for c in r if c]
        # 머리말 줄: 짧은 칸 2개 이상이고, 다음 행에 내용이 있다
        if len(cells) >= 2 and all(short(c) for c in cells) and i + 1 < len(rows) and len([c for c in rows[i + 1] if c]) >= 2 \
                and not all(short(c) for c in rows[i + 1] if c):
            head = [c[0] if c else "" for c in r]
            j = i + 1
            while j < len(rows) and not (len([c for c in rows[j] if c]) >= 2 and all(short(c) for c in rows[j] if c)
                                         and j + 1 < len(rows)):
                row = rows[j]
                off = max(0, len(head) - len(row))  # 왼쪽 칸이 합쳐진(rowspan) 행
                for k, c in enumerate(row):
                    if not c:
                        continue
                    h = head[k + off] if k + off < len(head) else ""
                    if h:
                        out.append("■ " + h)
                    out.extend(c)
                j += 1
            i = j
            continue
        # 왼쪽 머리말 행: 짧은 칸 | 내용
        if len(cells) == 2 and short(cells[0]) and not short(cells[1]):
            out.append("■ " + cells[0][0])
            out.extend(cells[1])
        elif cells and all(len(c) == 1 for c in cells):
            out.append(" | ".join(c[0] for c in cells))
        else:
            for c in cells:
                out.extend(c)
        i += 1
    return out


def html_text(page: str) -> str:
    """사람인 본문 페이지(relay view-detail) -> 보이는 글(구조 유지). 본문 칸이 없으면 ''."""
    m = BODY.search(page)
    if not m:
        return ""
    b = Builder()
    b.feed(m.group(1))
    return "\n".join(lines_of(b.root))
