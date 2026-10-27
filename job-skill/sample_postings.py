"""
새 샘플 수집: 사람인 검색 결과에서 직무별로 '본문이 이미지뿐인 공고'를 N건씩 고른다.

  - 검색: /zf_user/search/recruit (최신 등록순). 제목으로 직무를 한 번 더 거른다.
  - 판정: relay 본문(view-detail)의 글자(공백 제외)가 MAX_TEXT 미만이고, 템플릿이 아닌 이미지가 1장 이상이면 '이미지 전용'.
  - 요청 간격 1.2초(초당 1건 이하), User-Agent 는 프로젝트 이름(fetch_images.py 와 같다).
  - 결과: <출력 폴더>/targets.tsv (rec_idx, company, title, role), sampling_log.tsv(확인한 공고 전부), pages/ 캐시.
  - 이미 쓴 공고(--exclude 의 targets.tsv)는 건너뛴다.

실행: py -3.12 sample_postings.py --out sample2 --per-role 5
"""

from __future__ import annotations

import argparse
import csv
import html
from html.parser import HTMLParser
import os
import re
import sys
import urllib.parse

from fetch_images import RELAY, get, image_urls, is_template

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = ("https://www.saramin.co.kr/zf_user/search/recruit?searchType=search&searchword={kw}"
          "&recruitPage={page}&recruitSort={sort}&recruitPageCount=40")
ROLES = [
    {"role": "백엔드", "keywords": ["백엔드", "서버 개발", "Backend"], "sort": "reg_dt", "tag": "백엔드",
     "include": re.compile(r"백엔드|back-?\s?end|서버\s*개발", re.I),
     "exclude": re.compile(r"풀스택|full-?\s?stack|프론트", re.I)},
    {"role": "데이터 엔지니어", "keywords": ["데이터엔지니어", "데이터 엔지니어", "Data Engineer", "데이터 파이프라인", "데이터 플랫폼"],
     "sort": "relation", "tag": "데이터엔지니어",
     "include": re.compile(r"데이터\s*엔지니어|data\s*engineer|데이터\s*플랫폼|데이터\s*파이프라인|data\s*platform|"
                           r"데이터\s*인프라|빅\s*데이터\s*(개발|엔지니어)|\bETL\b", re.I),
     "exclude": re.compile(r"분석가|analyst|사이언티스트|scientist|라벨링|데이터\s*입력", re.I)},
]
MAX_TEXT = 100      # 본문 글자(공백 제외)가 이보다 적으면 이미지 전용으로 본다
MAX_CHECK = 150     # 직무당 본문을 열어 볼 최대 공고 수(요청 수 상한)
MAX_PAGES = 5       # 검색어당 볼 검색 결과 쪽 수(쪽당 40건)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def parse_items(page: str) -> list[tuple[str, str, str, list[str]]]:
    """검색 결과 -> [(제목, rec_idx, 회사, 사람인 직무 태그들)]."""
    out = []
    for b in page.split('<h2 class="job_tit">')[1:]:
        t = re.search(r'title="([^"]*)"', b)
        r = re.search(r'rec_idx=(\d+)', b)
        c = re.search(r'<strong class="corp_name">\s*<a[^>]*>\s*([^<]+?)\s*</a>', b)
        sec = re.search(r'<div class="job_sector">(.*?)</div>', b, re.S)
        if not (t and r and c):
            continue
        tags = [x.strip() for x in re.sub(r"<[^>]+>", ",", html.unescape(sec.group(1))).split(",")] if sec else []
        out.append((html.unescape(t.group(1)).strip(), r.group(1), html.unescape(c.group(1)).strip(), [x for x in tags if x]))
    return out


_BODY = re.compile(r'<div class="user_content">(.*?)<script', re.S)


_VOID = {"img", "br", "hr", "input", "meta", "link", "area", "col", "source", "wbr", "base", "param", "embed", "track"}
_HIDE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(px)?\s*(;|$)", re.I)


class _Visible(HTMLParser):
    """화면에 보이는 글만 모은다. 이미지형 공고는 같은 내용을 검색용으로 숨겨 두기도 한다
    (font-size:0, height:0 + overflow:hidden, display:none 등) — 그런 글은 세지 않는다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.parts = [], []

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            return
        st = (dict(attrs).get("style") or "").lower()
        hide = bool(_HIDE.search(st)) or (bool(re.search(r"height\s*:\s*0(px)?\s*(;|$)", st)) and "overflow" in st and "hidden" in st)
        self.stack.append((self.stack[-1] if self.stack else False) or hide or tag in ("script", "style"))

    def handle_endtag(self, tag):
        if tag not in _VOID and self.stack:
            self.stack.pop()

    def handle_data(self, d):
        if not (self.stack and self.stack[-1]):
            self.parts.append(d)


def visible_text(page: str) -> str | None:
    """본문(user_content)의 보이는 글. 본문 칸이 없으면 None."""
    m = _BODY.search(page)
    if not m:
        return None
    p = _Visible()
    p.feed(m.group(1))
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def body_stats(page: str) -> tuple[int, int]:
    """(본문의 보이는 글자 수(공백 제외), 사람인 양식이 아닌 이미지 수). 본문 칸이 없으면 (-1, 0)."""
    text = visible_text(page)
    if text is None:
        return -1, 0
    return len(text.replace(" ", "")), len([u for u in image_urls(page, "https://www.saramin.co.kr/") if not is_template(u)])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="sample2")
    ap.add_argument("--per-role", type=int, default=5)
    ap.add_argument("--exclude", default=os.path.join(HERE, "targets.tsv"))
    ap.add_argument("--role", help="이 직무만 다시 찾는다(다른 직무의 기존 결과는 유지)")
    args = ap.parse_args()
    out = os.path.join(HERE, args.out)
    pages = os.path.join(out, "pages")
    os.makedirs(pages, exist_ok=True)
    prev = list(csv.DictReader(open(args.exclude, encoding="utf-8"), delimiter="\t"))
    used = {r["rec_idx"] for r in prev}
    norm_co = lambda s: re.sub(r"\(주\)|㈜|주식회사|유한회사|\s", "", s)
    used_co = {norm_co(r["company"]) for r in prev}  # 처음 샘플의 회사도 빼서 새 회사로 채운다

    picked, log, seen = [], [], set(used)
    tpath, lpath = os.path.join(out, "targets.tsv"), os.path.join(out, "sampling_log.tsv")
    if args.role and os.path.exists(tpath):  # 다른 직무의 기존 결과 유지
        picked = [r for r in csv.DictReader(open(tpath, encoding="utf-8"), delimiter="\t") if r["role"] != args.role]
        log = [r for r in csv.DictReader(open(lpath, encoding="utf-8"), delimiter="\t") if r["role"] != args.role]
        used_co |= {norm_co(r["company"]) for r in picked}
        seen |= {r["rec_idx"] for r in log}
    for R in ROLES:
        if args.role and R["role"] != args.role:
            continue
        got, checked = 0, 0
        for kw in R["keywords"]:
            page_no = 1
            while got < args.per_role and checked < MAX_CHECK and page_no <= MAX_PAGES:
                status, _, raw = get(SEARCH.format(kw=urllib.parse.quote(kw), page=page_no, sort=R["sort"]))
                items = parse_items(raw.decode("utf-8", "replace")) if status == 200 else []
                print(f"[{R['role']}] '{kw}' 검색 {page_no}쪽: {len(items)}건", flush=True)
                if not items:
                    break
                for title, rid, company, tags in items:
                    role_ok = bool(R["include"].search(title)) or R["tag"] in tags  # 제목 또는 사람인 직무 태그
                    if rid in seen or not role_ok or R["exclude"].search(title):
                        continue
                    seen.add(rid)
                    if norm_co(company) in used_co:  # 회사당 1건
                        continue
                    path = os.path.join(pages, f"{rid}.html")
                    if os.path.exists(path):
                        page = open(path, encoding="utf-8").read()
                    else:
                        st, _, b = get(RELAY.format(id=rid))
                        page = b.decode("utf-8", "replace") if st == 200 else ""
                        if page:
                            open(path, "w", encoding="utf-8").write(page)
                    checked += 1
                    n_text, n_img = body_stats(page)
                    image_only = 0 <= n_text < MAX_TEXT and n_img >= 1
                    log.append({"role": R["role"], "rec_idx": rid, "company": company, "title": title,
                                "text_chars": n_text, "images": n_img, "image_only": int(image_only)})
                    print(f"   {rid} 글자 {n_text:>5} 이미지 {n_img} {'★ 이미지 전용' if image_only else ''} "
                          f"| {company} | {title[:40]}", flush=True)
                    if image_only:
                        picked.append({"rec_idx": rid, "company": company, "title": title, "role": R["role"]})
                        used_co.add(norm_co(company))
                        got += 1
                        if got >= args.per_role:
                            break
                page_no += 1
            if got >= args.per_role or checked >= MAX_CHECK:
                break
        print(f"[{R['role']}] {checked}건 확인, 이미지 전용 {got}건 고름", flush=True)

    with open(tpath, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rec_idx", "company", "title", "role"], delimiter="\t")
        w.writeheader()
        w.writerows(picked)
    with open(lpath, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(log[0]), delimiter="\t")
        w.writeheader()
        w.writerows(log)
    print(f"고른 공고 {len(picked)}건 -> {args.out}/targets.tsv")


if __name__ == "__main__":
    main()
