"""
공고 목록 수집 — Airflow ①·③ 의 첫 단계.

scan_lists: 사람인 직무 목록(백엔드 84, 데이터엔지니어 83)을 경력 필터(신입·경력 3년 이하·경력무관)를 켜고 끝까지 본다.
  두 직무 합쳐 약 15~28번 요청. 공고마다 마감일 글과 "3시간 전 수정" 같은 글도 읽는다.
select_targets: 새 공고 = 목록 − 아는 번호(DB 에 있는 공고). 아는 번호는 건너뛸 뿐 멈추지 않는다.
  교육생·4년 이상·경력 조건 모름은 버리고(본문 요청 없음) 이유를 돌려준다.
  두 번 돌려도 고른 공고는 DB 에 들어가 아는 번호가 되고, 버린 공고는 목록 글로 다시 버려져 새 공고 0건(멱등).
targets.tsv 에 쓰고, 본문을 받은 뒤 classify_targets 가 글/이미지 종류를 채운다.
요청은 fetch_images.get(간격 1.2초, 프로젝트 이름 UA)으로만 한다.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import os
import re
from zoneinfo import ZoneInfo

import fetch_images
from sample_postings import body_stats
from sample_random import LIST, ROLES, TRAINING, min_years, parse_list

TARGET_FIELDS = ["rec_idx", "company", "title", "role", "career", "deadline", "kind", "text_chars", "images"]
KST = ZoneInfo("Asia/Seoul")
MAX_YEARS = 3
# 사람인 경력 필터: 신입(exp_cd=1)·경력(2) 3년 이하(exp_max=3)·경력무관(exp_none=y) — 사용자 결정(사람인 필터를 믿음).
# 교육생은 이 필터로 걸러지지 않아 eligible 이 따로 버린다.
FILTER = "&exp_cd=1%2C2&exp_max=3&exp_none=y"
_ITEM = re.compile(r'<div id="rec-(\d+)" class="list_item[^"]*">(.*?)<div class="similar_recruit">', re.S)
_DATE = re.compile(r'<span class="date">\s*(.*?)\s*</span>', re.S)
_AGO = re.compile(r'<span class="deadlines">\s*(.*?)\s*</span>', re.S)
_UNIT = {"분": dt.timedelta(minutes=1), "시간": dt.timedelta(hours=1), "일": dt.timedelta(days=1)}


class ListFetchError(RuntimeError):
    """목록 쪽을 받지 못함(HTTP 오류·연결 실패). '목록 끝'으로 착각하지 않고 태스크를 실패시킨다."""


def _span(rx: re.Pattern, blk: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if (m := rx.search(blk)) else ""


def parse_items(page: str) -> list[dict]:
    """목록 HTML -> 공고들. sample_random.parse_list 결과 + deadline_text(마감일 글) + updated_text('3시간 전 수정' 같은 글)."""
    spans = {rid: (_span(_DATE, blk), _span(_AGO, blk)) for rid, blk in _ITEM.findall(page)}
    return [{**it, "deadline_text": spans.get(it["rec_idx"], ("", ""))[0],
             "updated_text": spans.get(it["rec_idx"], ("", ""))[1]} for it in parse_list(page)]


def parse_updated(text: str, now: dt.datetime) -> dt.datetime | None:
    """목록의 'N분/N시간/N일 전 수정' -> 늦게 잡은 수정 시각 now - (N-1)단위(N=0 이면 now).
    표시가 내림인지 반올림인지 몰라 한 단위 여유를 둔다 — 고친 것을 놓치느니 한 번 더 확인한다.
    '등록'·빈칸 -> None(고친 적 없음). 모르는 형식의 '수정' -> now(꼭 확인)."""
    t = (text or "").strip()
    if "수정" not in t:
        return None
    if m := re.search(r"(\d+)\s*(분|시간|일)\s*전", t):
        return now - max(int(m.group(1)) - 1, 0) * _UNIT[m.group(2)]
    return now


def parse_deadline(text: str, today: dt.date) -> dt.date | None:
    """'~11.15(일)', '~ 11/15(토)', 'D-6', 'D-day', '오늘마감', '내일마감' -> 날짜. 상시채용·채용시·빈칸 -> None.
    월·일만 있으면 올해로 보되, 오늘보다 60일 넘게 지난 날짜면 다음 해로 본다(12월에 '~01.05')."""
    t = (text or "").strip()
    if not t or "상시" in t or "채용시" in t:
        return None
    if "오늘" in t or re.search(r"D-?day", t, re.I):
        return today
    if "내일" in t:
        return today + dt.timedelta(days=1)
    if m := re.search(r"D-(\d+)", t):
        return today + dt.timedelta(days=int(m.group(1)))
    if m := re.search(r"(\d{1,2})\s*[./]\s*(\d{1,2})", t):
        month, day = int(m.group(1)), int(m.group(2))
        try:
            d = dt.date(today.year, month, day)
        except ValueError:
            return None
        return d.replace(year=today.year + 1) if (today - d).days > 60 else d
    return None


def eligible(career: str) -> tuple[bool, str]:
    """목록 경력 조건으로 대상인지. (True, '') 또는 (False, 이유)."""
    if TRAINING.search(career or ""):
        return False, "교육생"
    y = min_years(career or "")
    if y is None:
        return False, "경력 조건 모름"
    if y > MAX_YEARS:
        return False, "4년 이상"
    return True, ""


def write_targets(run_dir: str, rows: list[dict]) -> None:
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "targets.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TARGET_FIELDS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in TARGET_FIELDS} for r in rows)


def read_targets(run_dir: str) -> list[dict]:
    path = os.path.join(run_dir, "targets.tsv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _page_items(get, role: str, code: str, page_no: int) -> list[dict]:
    """목록 한 쪽. HTTP 오류, 또는 1쪽인데 공고가 0개(화면이 바뀌었거나 막힘)면 ListFetchError — '목록 끝'으로 착각하지 않게."""
    status, _, body = get(LIST.format(code=code, page=page_no) + FILTER)
    if status != 200:
        raise ListFetchError(f"{role} 목록 {page_no}쪽 HTTP {status}")
    items = parse_items(body.decode("utf-8", "replace"))
    if not items and page_no == 1:
        raise ListFetchError(f"{role} 목록 1쪽에 공고가 없음(화면이 바뀌었거나 막힘)")
    return items


def scan_lists(get=fetch_images.get, max_pages: int = 40, now: dt.datetime | None = None) -> dict[str, dict]:
    """두 직무 목록을 경력 필터를 켜고 끝까지 본다(연속 멈춤 없음).
    {공고번호: 목록 항목 + role + updated_at(parse_updated)}. 겹친 공고는 먼저 본 직무.
    빈 쪽이나, 이 직무에서 이미 본 공고만 있는 쪽(끝을 넘겨 마지막 쪽을 되풀이)이 나오면 그 직무는 끝."""
    now = now or dt.datetime.now(KST)
    listed: dict[str, dict] = {}
    for role, code in ROLES:
        seen: set[str] = set()
        for page_no in range(1, max_pages + 1):
            items = _page_items(get, role, code, page_no)
            if not items or all(it["rec_idx"] in seen for it in items):
                break
            for it in items:
                seen.add(it["rec_idx"])
                listed.setdefault(it["rec_idx"], {**it, "role": role, "updated_at": parse_updated(it["updated_text"], now)})
    return listed


def select_targets(listed: dict[str, dict], known: set[str], today: dt.date,
                   max_new: int | None = None) -> tuple[list[dict], list[tuple[str, str]]]:
    """(새 공고 targets 줄, 버린 공고 [(번호, 이유)]). 목록 순서(백엔드 → 데이터 엔지니어, 최신순) 그대로.
    max_new 는 시험용: 새 공고를 그 수까지만."""
    targets, excluded = [], []
    for no, it in listed.items():
        if no in known:
            continue
        ok, reason = eligible(it["career"])
        if not ok:
            excluded.append((no, reason))
            continue
        d = parse_deadline(it.get("deadline_text", ""), today)
        targets.append({"rec_idx": no, "company": it["company"], "title": it["title"], "role": it["role"],
                        "career": it["career"], "deadline": d.isoformat() if d else "",
                        "kind": "", "text_chars": "", "images": ""})
        if max_new is not None and len(targets) >= max_new:
            break
    return targets, excluded


def classify_targets(run_dir: str) -> dict[str, int]:
    """본문을 받은 뒤 글/이미지/섞임을 채운다. 본문이 없는 공고는 targets.tsv 에서 뺀다(규칙은 sample_random 과 같음)."""
    counts = {"글": 0, "이미지": 0, "섞임": 0, "본문 없음": 0}
    keep = []
    for r in read_targets(run_dir):
        path = os.path.join(run_dir, "pages", f"{r['rec_idx']}.html")
        n_text, n_img = body_stats(open(path, encoding="utf-8").read()) if os.path.exists(path) else (-1, 0)
        if n_text < 0:
            counts["본문 없음"] += 1
            continue
        kind = "이미지" if n_text < 100 and n_img >= 1 else ("글" if n_img == 0 else "섞임")
        counts[kind] += 1
        keep.append({**r, "kind": kind, "text_chars": str(n_text), "images": str(n_img)})
    write_targets(run_dir, keep)
    return counts
