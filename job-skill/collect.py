"""
공고 목록 수집 — Airflow ①·③ 의 첫 단계.

사람인 직무 목록(백엔드 84, 데이터엔지니어 83)을 최신순으로 한 쪽씩 받으면서
  - 이미 아는 공고번호(DB 에 있는 공고 + 버린 공고)가 연속 stop_after(5)개 나오면 그 직무를 멈춘다.
    그 앞의 처음 보는 공고만 새 공고다. 연속 수는 쪽을 넘어 이어진다.
  - 최소 요구 연수 4년 이상·교육생·경력 조건 모름은 버리고(본문 요청 없음) 이유를 돌려준다.
  - 두 직무 목록에 같이 나오는 공고는 먼저 본 직무 하나로만 넣는다.
    (이번 실행에서 고른 공고는 멈춤 규칙의 '아는 번호'로 세지 않는다 — 겹친 공고 때문에 일찍 멈추지 않게)
결과는 <run_dir>/targets.tsv. 본문을 받은 뒤 classify_targets 가 글/이미지 종류를 채운다.
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
_ITEM = re.compile(r'<div id="rec-(\d+)" class="list_item[^"]*">(.*?)<div class="similar_recruit">', re.S)
_DATE = re.compile(r'<span class="date">\s*(.*?)\s*</span>', re.S)


class ListFetchError(RuntimeError):
    """목록 쪽을 받지 못함(HTTP 오류·연결 실패). '목록 끝'으로 착각하지 않고 태스크를 실패시킨다."""


def parse_items(page: str) -> list[dict]:
    """목록 HTML -> 공고들. sample_random.parse_list 결과 + deadline_text(목록의 마감일 글 그대로)."""
    dates = {rid: re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if (m := _DATE.search(blk)) else ""
             for rid, blk in _ITEM.findall(page)}
    return [{**it, "deadline_text": dates.get(it["rec_idx"], "")} for it in parse_list(page)]


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


def _scan(items: list[dict], known: set[str], stop_after: int, run: int) -> tuple[list[dict], bool, int]:
    """(처음 보는 공고, 멈췄는지, 끝났을 때 이어지는 연속 수). 아는 번호가 연속 stop_after 개면 멈춘다."""
    new = []
    for it in items:
        if it["rec_idx"] in known:
            run += 1
            if run >= stop_after:
                return new, True, run
        else:
            run = 0
            new.append(it)
    return new, False, run


def select_new(items: list[dict], known: set[str], stop_after: int = 5) -> tuple[list[dict], bool]:
    """멈춘 곳 앞의 처음 보는 공고와 멈췄는지."""
    new, stopped, _ = _scan(items, known, stop_after, 0)
    return new, stopped


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


def collect_list(run_dir: str, known: set[str], get=fetch_images.get, max_pages: int = 40, stop_after: int = 5,
                 max_new: int | None = None, today: dt.date | None = None) -> dict:
    """두 직무 목록에서 새 공고를 골라 <run_dir>/targets.tsv 를 쓴다."""
    today = today or dt.datetime.now(KST).date()
    targets, excluded, taken = [], [], set()
    listed, stopped = 0, {}
    full = False
    for role, code in ROLES:
        run, stopped[role] = 0, False
        for page_no in range(1, max_pages + 1):
            if full:
                break
            url = LIST.format(code=code, page=page_no)
            status, _, body = get(url)
            if status != 200:
                raise ListFetchError(f"{role} 목록 {page_no}쪽 HTTP {status}")
            items = parse_items(body.decode("utf-8", "replace"))
            if not items:
                break
            listed += len(items)
            new, stop, run = _scan(items, known, stop_after, run)
            for it in new:
                no = it["rec_idx"]
                if no in taken:
                    continue
                taken.add(no)
                ok, reason = eligible(it["career"])
                if not ok:
                    excluded.append((no, reason))
                    continue
                d = parse_deadline(it["deadline_text"], today)
                targets.append({"rec_idx": no, "company": it["company"], "title": it["title"], "role": role,
                                "career": it["career"], "deadline": d.isoformat() if d else "",
                                "kind": "", "text_chars": "", "images": ""})
                if max_new is not None and len(targets) >= max_new:
                    full = True
                    break
            if stop:
                stopped[role] = True
                break
    write_targets(run_dir, targets)
    return {"targets": targets, "excluded": excluded, "listed": listed, "stopped": stopped}


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
