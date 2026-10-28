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
    assert [r["rec_idx"] for r in check] == ["A", "D"]          # D: 목록에서 사라짐 → 전체 페이지로 마감 확인
    assert [r["reason"] for r in check] == ["수정", "목록에 없음"]
    assert counts == {"진행": 4, "수정": 1, "목록에 없음": 1}


def test_select_recheck_takes_deadline_from_list():
    import recheck
    rows = [open_row("A", 3, deadline="2026-11-15"), open_row("B", 3, deadline="2026-11-15")]
    lst = {"A": listed(1, "~11.30(월)"), "B": listed(1, "상시채용")}
    check, _ = recheck.select_recheck(lst, rows, TODAY)
    assert [r["deadline"] for r in check] == ["2026-11-30", "2026-11-15"]   # 읽을 수 없는 마감일이면 DB 값 그대로


def test_blocked_responses_are_errors_not_closed(tmp_path):
    """403·429 같은 막힘은 마감이 아니다(마감은 되돌릴 수 없음). 404·410 과 본문 없는 200 만 마감."""
    import recheck
    rows = [row(n, "x" * 64) for n in ("A", "B", "C", "D")]
    get = FakeGet({"A": (403, "", b""), "B": (429, "", b""), "C": (400, "", b""), "D": (410, "", b"")})
    res = recheck.detect_changes(str(tmp_path), rows, get=get)
    assert res["error"] == ["A", "B", "C"] and res["closed"] == ["D"]



# ── 마감은 공고 전체 페이지(jobs/view)의 '접수마감' 표시로 — 본문 페이지(view-detail)는 마감돼도 200·본문 그대로 ──
VIEW_OPEN = '<html><span class="dday">D-8</span><button class="sri_btn_lg">지원하기</button></html>'
VIEW_CLOSED = '<html><span class="sri_btn_expired_apply" >접수마감</span><p class="copy end">마감되었습니다.</p></html>'


class SplitGet:
    """전체 페이지(jobs/view)와 본문 페이지(view-detail)를 따로 답한다. 받은 주소를 기록한다."""

    def __init__(self, view, body):
        self.view, self.body, self.urls = view, body, []

    def __call__(self, url, *a, **k):
        self.urls.append(url)
        no = url.split("rec_idx=")[1].split("&")[0]
        return (self.view if "/jobs/view?" in url else self.body)[no]


def gone(no, raw_hash):
    return {**row(no, raw_hash), "reason": "목록에 없음"}


def edited(no, raw_hash):
    return {**row(no, raw_hash), "reason": "수정"}


def test_gone_posting_is_closed_by_full_page_marker(tmp_path):
    import db_load
    import recheck
    base = page()
    h = lambda no: db_load.content_hash(base, no)
    rows = [gone("A", h("A")), gone("B", h("B")), gone("C", h("C")), gone("D", h("D")), edited("E", h("E"))]
    get = SplitGet(view={"A": ok(VIEW_CLOSED), "B": ok(VIEW_OPEN), "C": (404, "", b""), "D": (429, "", b"")},
                   body={"A": ok(base), "B": ok(base), "E": ok(page("지어낸 자격요건: Go 개발 경험"))})
    res = recheck.detect_changes(str(tmp_path), rows, get=get)
    assert res == {"changed": ["E"], "closed": ["A", "C"], "unchanged": ["B"], "error": ["D"]}
    viewed = sorted(u.split("rec_idx=")[1] for u in get.urls if "/jobs/view?" in u)
    assert viewed == ["A", "B", "C", "D"]                      # 수정된 공고(E)는 목록에 있어 마감 확인을 하지 않음


def test_detect_changes_adds_to_existing_targets(tmp_path):
    """① 에서는 targets.tsv 에 밀린·새 공고가 먼저 있다. 바뀐 공고는 그 뒤에 붙이고, 이미 있는 번호는 다시 넣지 않는다."""
    import collect
    import recheck
    collect.write_targets(str(tmp_path), [row("P", ""), row("B", "")])
    rows = [edited("B", "x" * 64), edited("C", "y" * 64)]
    recheck.detect_changes(str(tmp_path), rows, get=FakeGet({"B": ok(page()), "C": ok(page())}))
    assert [r["rec_idx"] for r in collect.read_targets(str(tmp_path))] == ["P", "B", "C"]
