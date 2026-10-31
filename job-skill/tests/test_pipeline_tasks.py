"""pipeline_tasks — Airflow 태스크 함수 시험. 실제 스크립트 실행(run_script)·DB·Slack 은 가짜로 바꾼다."""
from __future__ import annotations

import contextlib
import json
import os
import subprocess

import pytest

ROW = {"company": "(주)지어낸회사", "title": "지어낸 공고", "role": "백엔드", "career": "신입", "deadline": "",
       "kind": "", "text_chars": "", "images": ""}


@pytest.fixture
def pt(monkeypatch):
    import pipeline_tasks
    calls, sent = [], []
    monkeypatch.setattr(pipeline_tasks, "run_script",
                        lambda script, args, run_dir, **k: calls.append((script, list(args), *k.values())))
    monkeypatch.setattr(pipeline_tasks.notify, "send", lambda text: sent.append(text) or True)
    pipeline_tasks._calls, pipeline_tasks._sent = calls, sent
    return pipeline_tasks


def write_rows(run_dir, nos):
    import collect
    collect.write_targets(str(run_dir), [{"rec_idx": n, **ROW} for n in nos])


def alerts(run_dir) -> dict:
    """단계들이 결과 알림용으로 적어 둔 것(넘어간 공고·비용 상한)."""
    return json.load(open(os.path.join(str(run_dir), "alerts.json"), encoding="utf-8"))


def test_run_dir_for_sanitizes():
    import pipeline_tasks
    assert pipeline_tasks.run_dir_for("daily_collect", "scheduled__2026-10-28T00:00:00+09:00") == \
        "data/runs/daily_collect/scheduled__2026-10-28T00_00_00_09_00"


def test_empty_run_skips_everything(pt, tmp_path):
    write_rows(tmp_path, [])
    d = str(tmp_path)
    pt.step_fetch_raw(d)
    pt.step_ocr(d)
    pt.step_filter(d)
    pt.step_extract(d, budget_usd=5.0, limit=5.0)
    pt.step_load(d)
    assert pt._calls == [] and pt._sent == []
    assert pt.summary(d) == {"대상": 0, "추출": 0, "확인 필요": 0, "비용": 0.0}


def with_image(run_dir):
    img = run_dir / "images"
    img.mkdir()
    (img / "manifest.tsv").write_text("rec_idx\tseq\tfile\twidth\theight\tbytes\tstatus\turl\n"
                                      "A\t1\tA_1.png\t10\t10\t100\t200\thttps://example.com/a.png\n", encoding="utf-8")


def test_ocr_always_uses_gpu(pt, tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_PYTHON", "/opt/paddle/bin/python")  # 이미지 안의 OCR 전용 가상환경
    write_rows(tmp_path, ["A"])
    with_image(tmp_path)
    pt.step_ocr(str(tmp_path))
    assert pt._calls == [("dump_paddle_boxes.py", ["--gpu"], "/opt/paddle/bin/python")]


def test_ocr_python_defaults_to_current(pt, tmp_path, monkeypatch):
    import sys
    monkeypatch.delenv("OCR_PYTHON", raising=False)  # 노트북에서 바로 돌릴 때
    write_rows(tmp_path, ["A"])
    with_image(tmp_path)
    pt.step_ocr(str(tmp_path))
    assert pt._calls == [("dump_paddle_boxes.py", ["--gpu"], sys.executable)]


def test_ocr_failure_propagates(monkeypatch, tmp_path):
    import pipeline_tasks
    write_rows(tmp_path, ["A"])
    with_image(tmp_path)

    def boom(script, args, run_dir, **k):
        raise subprocess.CalledProcessError(1, script)

    monkeypatch.setattr(pipeline_tasks, "run_script", boom)
    with pytest.raises(subprocess.CalledProcessError):
        pipeline_tasks.step_ocr(str(tmp_path))


def test_extract_passes_budget_and_notes_stop(monkeypatch, tmp_path):
    import pipeline_tasks
    write_rows(tmp_path, ["A", "B"])
    ex = tmp_path / "out" / "extract"
    ex.mkdir(parents=True)
    (ex / "_budget.json").write_text('{"stopped": true, "spent": 0.5, "limit": 0.1, "left": 9}', encoding="utf-8")  # 지난 시도의 찌꺼기
    calls, sent = [], []

    def fake_run(script, args, run_dir):
        calls.append((script, list(args)))
        (ex / "_budget.json").write_text(json.dumps({"stopped": True, "spent": 1.5, "limit": 1.5, "left": 1}), encoding="utf-8")

    monkeypatch.setattr(pipeline_tasks, "run_script", fake_run)
    monkeypatch.setattr(pipeline_tasks.notify, "send", lambda text: sent.append(text) or True)
    res = pipeline_tasks.step_extract(str(tmp_path), budget_usd=1.5, limit=5.0)
    script, args = calls[0]
    assert script == "extract_skills.py" and "--tag=-ex" in args and args[args.index("--max-usd") + 1] == "1.5"
    assert args[args.index("--workers") + 1] == "8"                      # 공고 8건씩 동시에(OpenAI 한도 분당 200만 토큰의 약 15%)
    assert sent == [] and alerts(tmp_path)["budget"] == {"limit": 5.0, "left": 1}   # Slack 은 결과 알림에서 한 번에
    assert res["stopped"] is True


def test_extract_with_no_budget_left_skips_llm(pt, tmp_path):
    write_rows(tmp_path, ["A", "B", "C"])
    res = pt.step_extract(str(tmp_path), budget_usd=0, limit=5.0)
    assert pt._calls == [] and pt._sent == [] and alerts(tmp_path)["budget"] == {"limit": 5.0, "left": 3}
    assert res["stopped"] is True


def test_summary_counts_results(tmp_path):
    import pipeline_tasks
    write_rows(tmp_path, ["A", "B", "C"])
    d = tmp_path / "out" / "extract" / "gpt-5.6-luna-ex"
    d.mkdir(parents=True)
    (d / "A.json").write_text(json.dumps({"cost_usd": 0.004, "review_reasons": []}), encoding="utf-8")
    (d / "B.json").write_text(json.dumps({"cost_usd": 0.0035, "review_reasons": [{"검사": 1, "내용": "x"}]}), encoding="utf-8")
    assert pipeline_tasks.summary(str(tmp_path)) == {"대상": 3, "추출": 2, "확인 필요": 1, "비용": 0.0075}


def test_fetch_images_skips_existing_image(monkeypatch, tmp_path):
    import fetch_images
    (tmp_path / "pages").mkdir()
    (tmp_path / "images").mkdir()
    (tmp_path / "pages" / "A.html").write_text(
        '<div class="user_content"><img src="https://example.com/a.png"></div><script>', encoding="utf-8")
    from PIL import Image
    Image.new("RGB", (4, 4), "white").save(tmp_path / "images" / "A_1.png")
    monkeypatch.setattr(fetch_images, "PAGE_DIR", str(tmp_path / "pages"))
    monkeypatch.setattr(fetch_images, "IMG_DIR", str(tmp_path / "images"))
    monkeypatch.setattr(fetch_images, "MANIFEST", str(tmp_path / "images" / "manifest.tsv"))
    monkeypatch.setattr(fetch_images, "load_targets", lambda: [{"rec_idx": "A", "company": "가짜", "title": "가짜"}])
    urls = []
    monkeypatch.setattr(fetch_images, "get", lambda url, *a, **k: urls.append(url) or (500, "", b""))
    fetch_images.main()
    assert urls == []                                   # 본문도 이미지도 다시 받지 않음
    manifest = (tmp_path / "images" / "manifest.tsv").read_text(encoding="utf-8")
    assert "A_1.png" in manifest


# ── ② 수정 확인 태스크 ────────────────────────────────────────────────────
def test_detect_touches_unchanged_only(monkeypatch, tmp_path):
    import pipeline_tasks
    (tmp_path / "check.json").write_text(json.dumps([{"rec_idx": n, **ROW, "raw_hash": "h"} for n in "ABCD"]),
                                         encoding="utf-8")
    touched = []
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    stamps = []
    monkeypatch.setattr(pipeline_tasks.db_queries, "touch_checked",
                        lambda conn, nos, at=None: touched.extend(nos) or stamps.append(at) or len(nos))
    sent = []
    monkeypatch.setattr(pipeline_tasks.notify, "send", lambda text: sent.append(text) or True)
    monkeypatch.setattr(pipeline_tasks.recheck, "detect_changes",
                        lambda run_dir, rows: {"changed": ["B"], "closed": ["C"], "unchanged": ["A"], "error": ["D"]})
    res = pipeline_tasks.step_detect(str(tmp_path))
    assert touched == ["A"]          # 바뀐 공고는 다시 추출에 성공해야(DB 저장) 확인 시각이 바뀐다
    import datetime as dt
    assert stamps[0] is not None and stamps[0] <= dt.datetime.now(dt.timezone.utc)   # 본문을 받기 시작한 시각으로
    assert sent == [] and alerts(tmp_path)["확인 못 한 공고"] == [["D", "오류"]]   # 오류(D)는 결과 알림에 링크와 함께
    assert res == {"확인": 4, "바뀜": 1, "그대로": 1, "오류": 1}


def test_close_marks_closed(monkeypatch, tmp_path):
    import pipeline_tasks
    (tmp_path / "changes.json").write_text(json.dumps({"changed": [], "closed": ["C"], "unchanged": [], "error": []}),
                                           encoding="utf-8")
    closed = []
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "mark_closed", lambda conn, nos: closed.extend(nos) or len(nos))
    assert pipeline_tasks.step_close(str(tmp_path)) == 1 and closed == ["C"]


def result(base, dag_id, run, no, cost, run_at):
    d = base / dag_id / run / "out" / "extract" / "gpt-5.6-luna-ex"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{no}.json").write_text(json.dumps({"cost_usd": cost, "run_at": run_at}), encoding="utf-8")


def test_day_spent_counts_daily_only(tmp_path):
    """하루 상한은 ① 만(③ 은 따로 $10). 결과 파일의 run_at(UTC)을 KST 날짜로 센다 —
    DB 에 아직 안 들어간 결과(재시도·실패한 실행·같이 도는 실행)도 빠짐없이."""
    import datetime as dt
    import pipeline_tasks
    result(tmp_path, "daily_collect", "r1", "A", 1.0, "2026-10-28T03:00:00+00:00")     # KST 10/28 12:00
    result(tmp_path, "daily_collect", "r2", "B", 0.5, "2026-10-27T16:00:00+00:00")     # KST 10/28 01:00
    result(tmp_path, "daily_collect", "r0", "C", 3.0, "2026-10-27T14:00:00+00:00")     # KST 10/27 23:00 → 어제
    result(tmp_path, "backfill_once", "r3", "D", 6.0, "2026-10-28T03:00:00+00:00")     # ③ 은 세지 않음
    assert pipeline_tasks.day_spent(dt.date(2026, 10, 28), base=str(tmp_path)) == (1.5, 2)


def test_extract_budget(monkeypatch, tmp_path):
    import pipeline_tasks
    write_rows(tmp_path, ["A", "B"])
    d = tmp_path / "out" / "extract" / "gpt-5.6-luna-ex"
    d.mkdir(parents=True)
    (d / "A.json").write_text(json.dumps({"cost_usd": 1.25}), encoding="utf-8")
    assert pipeline_tasks.extract_budget(str(tmp_path), 10.0, daily=False) == 8.75   # ③: 이 실행에서 이미 쓴 것만
    monkeypatch.setattr(pipeline_tasks, "day_spent", lambda day, base=None: (3.0, 10))
    assert pipeline_tasks.extract_budget(str(tmp_path), 5.0, daily=True) == 2.0      # ①②: 오늘 ①+② 결과 파일(이 실행 포함)
    monkeypatch.setattr(pipeline_tasks, "day_spent", lambda day, base=None: (5.5, 10))
    assert pipeline_tasks.extract_budget(str(tmp_path), 5.0, daily=True) == 0.0


def test_load_does_not_record_excluded(monkeypatch, tmp_path):
    """버린 공고는 DB 에 기록하지 않는다(실행 폴더의 excluded.json 에만 남음). 새 공고가 없으면 DB 를 열지 않는다."""
    import pipeline_tasks
    order = []
    monkeypatch.setattr(pipeline_tasks, "run_script", lambda script, args, run_dir, **k: order.append(script))
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: pytest.fail("DB 를 열면 안 됨"))
    write_rows(tmp_path, ["A"])
    (tmp_path / "excluded.json").write_text('[["X9", "교육생"]]', encoding="utf-8")
    pipeline_tasks.step_load(str(tmp_path))
    assert order == ["db_load.py"]
    order.clear()
    write_rows(tmp_path, [])
    pipeline_tasks.step_load(str(tmp_path))
    assert order == []


def test_load_failure_is_reported_in_plain_words(monkeypatch, tmp_path):
    """저장 실패가 남으면 'DB 저장 실패 N건' 으로 태스크를 실패시킨다(Airflow 재시도 → Slack). 버린 공고는 기록하지 않는다."""
    import pipeline_tasks
    write_rows(tmp_path, ["D", "E"])
    (tmp_path / "excluded.json").write_text('[["X9", "4년 이상"]]', encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "load_result.json").write_text('{"total": {}, "failed": ["OLD"]}', encoding="utf-8")   # 지난 시도의 찌꺼기

    def fake_run(script, args, run_dir, **k):
        (out / "load_result.json").write_text(json.dumps({"total": {"공고": 0}, "failed": ["D", "E"], "why": {"D": "ValueError"}}),
                                              encoding="utf-8")
        raise subprocess.CalledProcessError(1, script)

    monkeypatch.setattr(pipeline_tasks, "run_script", fake_run)
    with pytest.raises(pipeline_tasks.notify.PostingsFailed, match="DB 저장 실패 2건") as e:
        pipeline_tasks.step_load(str(tmp_path))
    assert e.value.items == [("D", "ValueError"), ("E", "저장 실패")]


def test_load_returns_counts_for_the_log(monkeypatch, tmp_path):
    import pipeline_tasks
    write_rows(tmp_path, ["D"])
    out = tmp_path / "out"
    out.mkdir()

    def fake_run(script, args, run_dir, **k):
        (out / "load_result.json").write_text(json.dumps({"total": {"공고": 1, "추출 실행(새로)": 1}, "failed": []}),
                                              encoding="utf-8")

    monkeypatch.setattr(pipeline_tasks, "run_script", fake_run)
    assert pipeline_tasks.step_load(str(tmp_path)) == {"공고": 1, "추출 실행(새로)": 1}



# ── ① 매일 수집: 목록 전체 → 새 공고 + 수정·사라진 공고 고르기 + 마감일 반영 ──────
def item(no, career="신입", updated_at=None, deadline_text=""):
    return {"rec_idx": no, "title": "지어낸 공고", "company": "(주)지어낸회사", "career": career, "role": "백엔드",
            "deadline_text": deadline_text, "updated_text": "", "updated_at": updated_at}


@pytest.fixture
def daily(monkeypatch):
    """DB·사람인을 가짜로. 호출을 기록한다."""
    import datetime as dt
    import pipeline_tasks
    calls = {}
    checked = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "today_kst", lambda: dt.date(2026, 10, 28))
    monkeypatch.setattr(pipeline_tasks.db_queries, "known_posting_nos", lambda conn: {"K1", "O1", "O2"})
    monkeypatch.setattr(pipeline_tasks.db_queries, "pending_postings", lambda conn: [{"rec_idx": "P1", **ROW}])
    monkeypatch.setattr(pipeline_tasks.db_queries, "open_postings", lambda conn: [
        {"rec_idx": n, **ROW, "raw_hash": "h", "last_checked_at": checked} for n in ("O1", "O2")])
    monkeypatch.setattr(pipeline_tasks.db_queries, "update_deadlines", lambda conn, m: calls.setdefault("deadlines", m) and len(m))
    monkeypatch.setattr(pipeline_tasks.collect, "scan_lists", lambda **k: {
        "N1": item("N1"), "K1": item("K1"), "P1": item("P1"), "N2": item("N2", deadline_text="~11.30(월)"),
        "X9": item("X9", career="교육생"),
        "O1": item("O1", updated_at=checked + dt.timedelta(days=1), deadline_text="~11.20(금)")})   # O1 수정, O2 사라짐
    pipeline_tasks._calls = calls
    return pipeline_tasks


def test_daily_collect_writes_targets_check_and_excluded(daily, tmp_path):
    res = daily.step_collect(str(tmp_path), include_pending=True)
    assert [r["rec_idx"] for r in daily.collect.read_targets(str(tmp_path))] == ["P1", "N1", "N2"]   # 밀린 공고 먼저, 아는 번호 건너뜀
    assert json.loads((tmp_path / "excluded.json").read_text(encoding="utf-8")) == [["X9", "교육생"]]
    check = json.loads((tmp_path / "check.json").read_text(encoding="utf-8"))
    assert [(r["rec_idx"], r["reason"]) for r in check] == [("O1", "수정"), ("O2", "목록에 없음")]
    assert res == {"new": 2, "pending": 1, "excluded": 1, "진행": 2, "수정": 1, "목록에 없음": 1, "마감일 바뀜": 2}


def test_daily_collect_updates_deadlines_from_list(daily, tmp_path):
    import datetime as dt
    daily.step_collect(str(tmp_path), include_pending=True)
    assert daily._calls["deadlines"] == {"N2": dt.date(2026, 11, 30), "O1": dt.date(2026, 11, 20)} or \
        daily._calls["deadlines"] == {"O1": dt.date(2026, 11, 20), "N2": dt.date(2026, 11, 30)}


def test_backfill_collect_has_no_recheck(daily, monkeypatch, tmp_path):
    """③ 은 밀린 공고·수정 확인 없이 새 공고만(목록 끝까지, 아는 번호 건너뜀)."""
    monkeypatch.setattr(daily.db_queries, "open_postings", lambda conn: pytest.fail("③ 은 수정 확인 안 함"))
    res = daily.step_collect(str(tmp_path), include_pending=False)
    assert [r["rec_idx"] for r in daily.collect.read_targets(str(tmp_path))] == ["N1", "P1", "N2"]
    assert not (tmp_path / "check.json").exists() and res == {"new": 3, "pending": 0, "excluded": 1}


def test_detect_and_close_without_check_file(monkeypatch, tmp_path):
    """③ 처럼 check.json·changes.json 이 없으면 아무것도 안 한다."""
    import pipeline_tasks
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: pytest.fail("DB 를 열면 안 됨"))
    assert pipeline_tasks.step_detect(str(tmp_path)) == {"확인": 0, "바뀜": 0, "그대로": 0, "오류": 0}
    assert pipeline_tasks.step_close(str(tmp_path)) == 0


def test_extract_failures_are_alerted(monkeypatch, tmp_path):
    """공고 하나하나의 LLM 추출 실패는 태스크를 멈추지 않고, 숫자·원인만 Slack 으로 알린다(공고번호는 넣지 않음)."""
    import pipeline_tasks
    write_rows(tmp_path, ["A", "B", "C"])
    ex = tmp_path / "out" / "extract"
    ex.mkdir(parents=True)
    (ex / "_stats.json").write_text('[{"failed": ["OLD"], "fail_reasons": {"x": 1}}]', encoding="utf-8")   # 지난 시도의 찌꺼기
    sent = []

    def fake_run(script, args, run_dir, **k):
        (ex / "_stats.json").write_text(json.dumps([{"failed": ["A", "B"], "fail_reasons": {"응답 잘림·형식 오류": 2},
                                                     "fail_detail": {"A": "응답 잘림·형식 오류", "B": "응답 잘림·형식 오류"}}]),
                                        encoding="utf-8")

    monkeypatch.setattr(pipeline_tasks, "run_script", fake_run)
    monkeypatch.setattr(pipeline_tasks.notify, "send", lambda text: sent.append(text) or True)
    res = pipeline_tasks.step_extract(str(tmp_path), budget_usd=5.0, limit=5.0)
    assert sent == [] and res["failed"] == 2
    assert alerts(tmp_path)["LLM 추출 실패"] == [["A", "응답 잘림·형식 오류"], ["B", "응답 잘림·형식 오류"]]


def test_extract_without_failures_sends_nothing(monkeypatch, tmp_path):
    import pipeline_tasks
    write_rows(tmp_path, ["A"])
    ex = tmp_path / "out" / "extract"
    ex.mkdir(parents=True)
    sent = []
    monkeypatch.setattr(pipeline_tasks, "run_script", lambda script, args, run_dir, **k: (ex / "_stats.json").write_text(
        json.dumps([{"failed": [], "fail_reasons": {}}]), encoding="utf-8"))
    monkeypatch.setattr(pipeline_tasks.notify, "send", lambda text: sent.append(text) or True)
    assert pipeline_tasks.step_extract(str(tmp_path), budget_usd=5.0, limit=5.0)["failed"] == 0
    assert sent == [] and alerts(tmp_path)["LLM 추출 실패"] == []



def test_fetch_raw_alerts_postings_without_body(monkeypatch, tmp_path):
    """본문을 못 받아 빠진 공고는 공고번호·링크·원인을 알린다(다음 실행 때 다시)."""
    import pipeline_tasks
    write_rows(tmp_path, ["A", "B"])
    sent = []

    def fake_fetch(script, args, run_dir, **k):
        (tmp_path / "pages").mkdir(exist_ok=True)
        (tmp_path / "pages" / "A.html").write_text('<div class="user_content"><p>지어낸 본문</p></div><script>', encoding="utf-8")
        (tmp_path / "images").mkdir(exist_ok=True)
        (tmp_path / "images" / "skipped.tsv").write_text("rec_idx\treason\nA\t본문 이미지 없음\nB\tHTTP 404\n", encoding="utf-8")

    monkeypatch.setattr(pipeline_tasks, "run_script", fake_fetch)
    monkeypatch.setattr(pipeline_tasks.notify, "send", lambda text: sent.append(text) or True)
    pipeline_tasks.step_fetch_raw(str(tmp_path))
    assert [r["rec_idx"] for r in pipeline_tasks.collect.read_targets(str(tmp_path))] == ["A"]
    assert sent == [] and alerts(tmp_path)["본문을 못 받은 공고"] == [["B", "HTTP 404"]]


def test_detect_alerts_postings_it_could_not_check(monkeypatch, tmp_path):
    import pipeline_tasks
    (tmp_path / "check.json").write_text(json.dumps([{"rec_idx": "D", **ROW, "raw_hash": "h"}]), encoding="utf-8")
    sent = []
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "touch_checked", lambda conn, nos, at=None: len(nos))
    monkeypatch.setattr(pipeline_tasks.notify, "send", lambda text: sent.append(text) or True)
    monkeypatch.setattr(pipeline_tasks.recheck, "detect_changes", lambda run_dir, rows: {
        "changed": [], "closed": [], "unchanged": [], "error": ["D"], "why": {"D": "HTTP 429"}})
    pipeline_tasks.step_detect(str(tmp_path))
    assert sent == [] and alerts(tmp_path)["확인 못 한 공고"] == [["D", "HTTP 429"]]


def _report_run(tmp_path, budget=False):
    """대상 A·B·C·E: A 는 추출됨(확인 필요), B 는 LLM 실패, C·E 는 결과 없음. 변경 감지에서 D 확인 못 함."""
    write_rows(tmp_path, ["A", "B", "C", "E"])
    d = tmp_path / "out" / "extract" / "gpt-5.6-luna-ex"
    d.mkdir(parents=True)
    (d / "A.json").write_text(json.dumps({"cost_usd": 0.73, "review_reasons": [{"검사": 2, "내용": "x"}]}), encoding="utf-8")
    note = {"확인 못 한 공고": [["D", "HTTP 429"]], "LLM 추출 실패": [["B", "응답 잘림·형식 오류"]]}
    if budget:
        note["budget"] = {"limit": 5.0, "left": 2}
    (tmp_path / "alerts.json").write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")


def test_daily_report_is_one_message(tmp_path):
    import pipeline_tasks
    _report_run(tmp_path)
    got = {"new": 3, "pending": 1, "수정": 14, "목록에 없음": 55, "마감일 바뀜": 12}
    msg = pipeline_tasks.daily_report(str(tmp_path), got, {"바뀜": 2, "오류": 1}, closed=55, today_cost=0.73)
    url = "https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=list&rec_idx="
    assert msg.splitlines() == [
        "✅ 매일 수집 완료",
        "• 수집: 새 공고 3 · 밀린 공고 1",
        "• 변경 감지: 수정 14 → 바뀜 2 · 마감일 바뀜 12 · 확인 오류 1",
        "• 마감: 목록에 없음 55 → 마감 55",
        "• 추출: 1/4건 · 확인 필요 1",
        "• 비용: 이번 $0.73 · 오늘 $0.73 (하루 상한 $5)",
        "⚠️ 넘어간 공고 4건 — 다음 실행 때 다시 시도",
        f"• <{url}D|D> 확인 못 한 공고 · HTTP 429",
        f"• <{url}B|B> LLM 추출 실패 · 응답 잘림·형식 오류",
        f"• <{url}C|C> 추출할 글 없음",
        f"• <{url}E|E> 추출할 글 없음",
    ]


def test_report_does_not_call_budget_stop_no_text(tmp_path):
    """비용 상한으로 멈춰 결과가 없는 공고는 '글 없음'이 아니라 상한 줄의 '남은 공고'로 센다."""
    import pipeline_tasks
    _report_run(tmp_path, budget=True)
    msg = pipeline_tasks.backfill_report(str(tmp_path), {"new": 4, "excluded": 7})
    assert "추출할 글 없음" not in msg and "남은 공고 2건" in msg
    assert msg.splitlines()[:4] == ["✅ 전체 수집 완료", "• 수집: 대상 공고 4 · 제외 7", "• 추출: 1/4건 · 확인 필요 1",
                                    "• 비용: $0.73 (상한 $10)"]


def _dictionary_run(monkeypatch, tmp_path, note: dict, fail: bool = False):
    """가짜 추출: _dictionary.json 에 note 를 쓰고(fail 이면 스크립트가 실패한 것처럼) step_extract 를 돌린다."""
    import pipeline_tasks
    write_rows(tmp_path, ["A"])
    ex = tmp_path / "out" / "extract"
    ex.mkdir(parents=True)

    def fake_run(script, args, run_dir, **k):
        (ex / "_dictionary.json").write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        if fail:
            raise subprocess.CalledProcessError(1, ["extract_skills.py"])
        (ex / "_stats.json").write_text(json.dumps([{"failed": [], "fail_reasons": {}}]), encoding="utf-8")

    monkeypatch.setattr(pipeline_tasks, "run_script", fake_run)
    return pipeline_tasks.step_extract(str(tmp_path), budget_usd=5.0, limit=5.0)


def test_dictionary_problems_go_to_result_report(monkeypatch, tmp_path):
    """팀원이 사전을 조금 어긋나게 고쳤으면 추출은 계속하고, 결과 알림에 '사전 확인 필요'로 적는다."""
    import notify
    import pipeline_tasks
    problems = ["같은 이름·별칭 'aws' 이 기술 AWS, Lambda 에 겹침 (AWS 로 씀)", "능력이 없는 사용 중 기술: Kubernetes"]
    _dictionary_run(monkeypatch, tmp_path, {"version": "abc", "fatal": [], "problems": problems})
    assert alerts(tmp_path)["사전 확인 필요"] == problems
    skipped, budget, dictionary = pipeline_tasks.run_alerts(str(tmp_path))
    msg = notify.msg_report("매일 수집", [], skipped, budget, dictionary)
    assert "⚠️ 사전 확인 필요 2건 (추출은 계속함)" in msg.splitlines()
    assert f"• {problems[1]}" in msg.splitlines()


def test_broken_dictionary_fails_task_with_reason(monkeypatch, tmp_path):
    """사전이 통째로 망가졌으면 추출 태스크가 이유와 함께 실패한다(Airflow 실패 알림에 이유가 보이게)."""
    with pytest.raises(RuntimeError, match="사전이 망가져 추출을 멈춤: '기타' 능력이 없거나 꺼짐"):
        _dictionary_run(monkeypatch, tmp_path, {"version": "", "fatal": ["'기타' 능력이 없거나 꺼짐"], "problems": []}, fail=True)


def test_report_without_dictionary_problems_has_no_dictionary_line(tmp_path):
    import pipeline_tasks
    _report_run(tmp_path)
    assert pipeline_tasks.run_alerts(str(tmp_path))[2] == []
    assert "사전 확인 필요" not in pipeline_tasks.backfill_report(str(tmp_path), {"new": 4, "excluded": 7})
