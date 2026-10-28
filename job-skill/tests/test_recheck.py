"""recheck.detect_changes — 본문을 다시 받아 지문 비교 (가짜 사람인, 지어낸 본문)."""
from __future__ import annotations

import json
import os

import pytest

BODY = '<html><div class="user_content"><p>지어낸 자격요건: Java 개발 경험</p>{noise}</div><script></script></html>'


def page(text="지어낸 자격요건: Java 개발 경험", color="#089ed7"):
    return BODY.replace("지어낸 자격요건: Java 개발 경험", text).format(noise=f'<font color="{color}"></font>')


def row(no, raw_hash):
    return {"rec_idx": no, "company": "(주)지어낸회사", "title": "지어낸 공고", "role": "백엔드", "career": "신입",
            "deadline": "", "raw_hash": raw_hash}


class FakeGet:
    def __init__(self, answers):
        self.answers = answers

    def __call__(self, url, *a, **k):
        no = url.split("rec_idx=")[1].split("&")[0]
        return self.answers[no]


def ok(html):
    return 200, "text/html", html.encode("utf-8")


def test_detect_changes_splits_three_ways(tmp_path):
    import collect
    import db_load
    import recheck
    base = page()
    rows = [row("A", db_load.content_hash(base, "A")), row("B", db_load.content_hash(base, "B")), row("C", "c" * 64)]
    get = FakeGet({"A": ok(base), "B": ok(page("지어낸 자격요건: Java·Kotlin 개발 경험")), "C": (404, "", b"")})
    res = recheck.detect_changes(str(tmp_path), rows, get=get)
    assert res == {"changed": ["B"], "closed": ["C"], "unchanged": ["A"], "error": []}
    assert (tmp_path / "pages" / "B.html").exists() and not (tmp_path / "pages" / "A.html").exists()
    assert [r["rec_idx"] for r in collect.read_targets(str(tmp_path))] == ["B"]
    assert json.loads((tmp_path / "changes.json").read_text(encoding="utf-8")) == res


def test_font_color_noise_is_not_a_change(tmp_path):
    import db_load
    import recheck
    rows = [row("A", db_load.content_hash(page(color="#089ed7"), "A"))]
    res = recheck.detect_changes(str(tmp_path), rows, get=FakeGet({"A": ok(page(color="#4bd789"))}))
    assert res["unchanged"] == ["A"] and res["changed"] == []


def test_page_without_body_is_closed(tmp_path):
    import recheck
    res = recheck.detect_changes(str(tmp_path), [row("A", "a" * 64)], get=FakeGet({"A": ok("<html>마감된 공고입니다</html>")}))
    assert res["closed"] == ["A"]


def test_connection_error_is_not_closed(tmp_path):
    import recheck
    rows = [row("A", "a" * 64), row("B", "b" * 64)]
    res = recheck.detect_changes(str(tmp_path), rows, get=FakeGet({"A": (None, "", b""), "B": (503, "", b"")}))
    assert res["error"] == ["A", "B"] and res["closed"] == []


# ── 목록 기반 고르기: 마지막 확인 뒤 '수정'된 공고 + 목록에서 사라진 공고만 본문을 받는다 ──
import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=KST)
TODAY = NOW.date()


def open_row(no, checked_days_ago, deadline=""):
    return {**row(no, "h" * 64), "deadline": deadline, "last_checked_at": NOW - dt.timedelta(days=checked_days_ago)}


def listed(updated_days_ago=None, deadline_text=""):
    at = None if updated_days_ago is None else NOW - dt.timedelta(days=updated_days_ago)
    return {"updated_at": at, "deadline_text": deadline_text}


def test_select_recheck_picks_modified_and_gone():
    import recheck
    rows = [open_row("A", 3), open_row("B", 3), open_row("C", 3), open_row("D", 3)]
    lst = {"A": listed(1),        # 마지막 확인(3일 전) 뒤에 수정 → 확인
           "B": listed(5),        # 수정이 마지막 확인보다 앞 → 이미 본 본문
           "C": listed(None),     # 등록만(고친 적 없음)
           "X": listed(0)}        # DB 에 없는 공고는 ① 몫
    check, counts = recheck.select_recheck(lst, rows, TODAY)
    assert [r["rec_idx"] for r in check] == ["A", "D"]          # D: 목록에서 사라짐 → 본문으로 마감 확인
    assert counts == {"진행": 4, "수정": 1, "목록에 없음": 1}


def test_select_recheck_takes_deadline_from_list():
    import recheck
    rows = [open_row("A", 3, deadline="2026-11-15"), open_row("B", 3, deadline="2026-11-15")]
    lst = {"A": listed(1, "~11.30(월)"), "B": listed(1, "상시채용")}
    check, _ = recheck.select_recheck(lst, rows, TODAY)
    assert [r["deadline"] for r in check] == ["2026-11-30", "2026-11-15"]   # 읽을 수 없는 마감일이면 DB 값 그대로
