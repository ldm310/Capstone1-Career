"""collect.py — 공고 목록 수집 시험 (사람인에 요청하지 않음, 지어낸 목록 HTML 사용)."""
from __future__ import annotations

import datetime as dt
import os

import pytest

from conftest import HERE

FIXTURE = os.path.join(HERE, "tests", "fixtures", "list_page.html")
TODAY = dt.date(2026, 10, 28)


def page():
    return open(FIXTURE, encoding="utf-8").read()


def nos(rows):
    return [r["rec_idx"] for r in rows]


def test_parse_items_reads_fixture():
    import collect
    items = collect.parse_items(page())
    assert nos(items) == ["9000007", "9000006", "9000005", "9000004", "9000003", "9000002", "9000001"]
    assert items[1]["career"] == "1 ~ 3년 · 정규직"
    assert [i["deadline_text"] for i in items] == ["~11.15(일)", "D-6", "~11.20(금)", "상시채용", "채용시", "~12.01(화)", "~11.30(월)"]
    assert items[0]["company"] == "(주)가나소프트" and items[0]["title"] == "백엔드 개발자 신입 채용"


@pytest.mark.parametrize("text,expected", [
    ("~11.15(일)", dt.date(2026, 11, 15)),
    ("~ 11/15(토)", dt.date(2026, 11, 15)),
    ("~01.05(월)", dt.date(2027, 1, 5)),
    ("~ 01/05(월)", dt.date(2027, 1, 5)),
    ("D-6", dt.date(2026, 11, 3)),
    ("D-day", dt.date(2026, 10, 28)),
    ("오늘마감", dt.date(2026, 10, 28)),
    ("내일마감", dt.date(2026, 10, 29)),
    ("상시채용", None),
    ("채용시", None),
    ("채용시 마감", None),
    ("", None),
])
def test_parse_deadline_cases(text, expected):
    import collect
    assert collect.parse_deadline(text, TODAY) == expected


def test_eligible():
    import collect
    assert collect.eligible("신입 · 경력") == (True, "")
    assert collect.eligible("경력 3년↑ · 정규직") == (True, "")
    assert collect.eligible("경력 5년↑ · 정규직") == (False, "4년 이상")
    assert collect.eligible("신입 · 교육생") == (False, "교육생")
    assert collect.eligible("정규직") == (False, "경력 조건 모름")


def items_of(numbers):
    return [{"rec_idx": str(n)} for n in numbers]


def test_classify_targets(tmp_path):
    import collect
    rows = [{"rec_idx": n, "company": "가짜", "title": "가짜", "role": "백엔드", "career": "신입", "deadline": "",
             "kind": "", "text_chars": "", "images": ""} for n in ("T", "I", "N")]
    collect.write_targets(str(tmp_path), rows)
    (tmp_path / "pages").mkdir()
    long_text = "지어낸 자격요건 문장입니다 " * 20
    (tmp_path / "pages" / "T.html").write_text(f'<div class="user_content"><p>{long_text}</p></div><script>', encoding="utf-8")
    (tmp_path / "pages" / "I.html").write_text('<div class="user_content"><img src="https://example.com/a.png"></div><script>', encoding="utf-8")
    (tmp_path / "pages" / "N.html").write_text("<html>본문 칸 없음</html>", encoding="utf-8")
    counts = collect.classify_targets(str(tmp_path))
    after = {r["rec_idx"]: r for r in collect.read_targets(str(tmp_path))}
    assert set(after) == {"T", "I"}
    assert after["T"]["kind"] == "글" and after["I"]["kind"] == "이미지"
    assert counts == {"글": 1, "이미지": 1, "섞임": 0, "본문 없음": 1}


# ── ② 수정 확인용: 목록 전체 보기 ──────────────────────────────────────────
NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))


def test_parse_items_reads_updated_text():
    import collect
    items = collect.parse_items(page())
    assert [i["updated_text"] for i in items] == ["2시간 전 등록", "3시간 전 수정", "2시간 전 등록", "1일 전 등록",
                                                  "2시간 전 등록", "4일 전 수정", "2시간 전 등록"]


@pytest.mark.parametrize("text,expected", [
    ("3시간 전 수정", NOW - dt.timedelta(hours=2)),     # 늦게 잡음: 한 단위 여유(반올림 표시여도 놓치지 않게)
    ("2일 전 수정", NOW - dt.timedelta(days=1)),
    ("15분 전 수정", NOW - dt.timedelta(minutes=14)),
    ("0분 전 수정", NOW),
    ("10/20 수정", NOW),                                # 모르는 형식의 '수정' → 지금(꼭 확인)
    ("5일 전 등록", None),                              # 고친 적 없음
    ("", None),
])
def test_parse_updated(text, expected):
    import collect
    assert collect.parse_updated(text, NOW) == expected


class PagedGet:
    """두 직무 1쪽은 fixture. 백엔드 2쪽은 1쪽을 되풀이(끝을 넘긴 쪽), 데이터 엔지니어 2쪽은 빈 목록."""

    def __init__(self, status=200):
        self.urls, self.status = [], status

    def __call__(self, url, *a, **k):
        self.urls.append(url)
        if self.status != 200:
            return self.status, "", b""
        full = "page=1&" in url or ("cat_kewd=84&" in url and "page=2&" in url)
        return 200, "text/html", (page() if full else "<html></html>").encode("utf-8")


def test_scan_lists_reads_every_page_without_stopping():
    import collect
    get = PagedGet()
    listed = collect.scan_lists(get=get, now=NOW)
    assert sorted(listed) == ["9000001", "9000002", "9000003", "9000004", "9000005", "9000006", "9000007"]
    assert len(get.urls) == 4       # 백엔드 1·2쪽(되풀이 → 끝) + 데이터 엔지니어 1·2쪽(빈 목록 → 끝)
    assert {v["role"] for v in listed.values()} == {"백엔드"}     # 겹친 공고는 먼저 본 직무
    assert listed["9000006"]["updated_at"] == NOW - dt.timedelta(hours=2)
    assert listed["9000007"]["updated_at"] is None and listed["9000007"]["deadline_text"] == "~11.15(일)"


def test_scan_lists_raises_on_list_error():
    import collect
    with pytest.raises(collect.ListFetchError):
        collect.scan_lists(get=PagedGet(status=503), now=NOW)


# ── 최종 검토 고침 ─────────────────────────────────────────────────────────
class AllPagesGet:
    """모든 쪽이 fixture(끝을 넘긴 쪽에서 마지막 쪽을 되풀이하는 사람인 흉내). empty_first 면 모든 쪽이 빈 목록."""

    def __init__(self, empty_first=False):
        self.urls, self.empty_first = [], empty_first

    def __call__(self, url, *a, **k):
        self.urls.append(url)
        return 200, "text/html", ("<html></html>" if self.empty_first else page()).encode("utf-8")


def test_empty_first_page_is_an_error(tmp_path):
    """목록 1쪽이 200인데 공고가 0개 = 화면이 바뀌었거나 막힌 것. '목록 끝'으로 보고 조용히 0건으로 끝내지 않는다."""
    import collect
    with pytest.raises(collect.ListFetchError):
        collect.scan_lists(get=AllPagesGet(empty_first=True), now=NOW)


# ── ① 매일 수집: 목록 전체에서 새 공고 고르기(연속 멈춤 없음) ─────────────────
def test_select_targets_skips_known_and_excludes():
    import collect
    listed = collect.scan_lists(get=PagedGet(), now=NOW)
    targets, excluded = collect.select_targets(listed, known={"9000007"}, today=TODAY)
    assert nos(targets) == ["9000006", "9000004", "9000002", "9000001"]       # 아는 번호는 건너뜀(멈추지 않음)
    assert sorted(excluded) == [("9000003", "교육생"), ("9000005", "4년 이상")]
    by = {r["rec_idx"]: r for r in targets}
    assert by["9000006"]["deadline"] == "2026-11-03" and by["9000004"]["deadline"] == ""
    assert by["9000006"]["role"] == "백엔드" and set(targets[0]) >= set(collect.TARGET_FIELDS)


def test_select_targets_twice_gives_nothing_new():
    """멱등성: 고른 공고와 버린 공고가 '아는 번호'가 되면 두 번째에는 새 공고 0건."""
    import collect
    listed = collect.scan_lists(get=PagedGet(), now=NOW)
    targets, excluded = collect.select_targets(listed, known=set(), today=TODAY)
    known = set(nos(targets)) | {no for no, _ in excluded}
    assert collect.select_targets(listed, known=known, today=TODAY) == ([], [])


def test_select_targets_respects_max_new():
    import collect
    listed = collect.scan_lists(get=PagedGet(), now=NOW)
    targets, _ = collect.select_targets(listed, known=set(), today=TODAY, max_new=2)
    assert nos(targets) == ["9000007", "9000006"]


def test_list_requests_use_career_filter():
    """사람인 경력 필터(신입·경력 3년 이하·경력무관)를 켠 목록만 받는다(사용자 결정)."""
    import collect
    get = PagedGet()
    collect.scan_lists(get=get, now=NOW)
    assert get.urls and all("exp_cd=1%2C2&exp_max=3&exp_none=y" in u for u in get.urls)
