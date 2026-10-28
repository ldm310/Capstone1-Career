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
    pt.step_extract(d, budget_usd=5.0, dag_label="매일 수집", limit=5.0)
    pt.step_load(d)
    assert pt._calls == [] and pt._sent == []
    assert pt.summary(d) == {"새 공고": 0, "추출": 0, "확인 필요": 0, "비용": 0.0}


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


def test_collect_puts_pending_first(monkeypatch, tmp_path):
    import collect
    import pipeline_tasks
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "known_posting_nos", lambda conn: set())
    monkeypatch.setattr(pipeline_tasks.db_queries, "pending_postings", lambda conn: [{"rec_idx": "P1", **ROW}])
    monkeypatch.setattr(pipeline_tasks.db_queries, "record_excluded", lambda conn, rows: len(rows))

    def fake_collect(run_dir, known, max_new=None, **k):
        rows = [{"rec_idx": n, **ROW} for n in ("N1", "P1", "N2")]
        collect.write_targets(run_dir, rows)
        return {"targets": rows, "excluded": [("X9", "4년 이상")], "listed": 4, "stopped": {}}

    monkeypatch.setattr(pipeline_tasks.collect, "collect_list", fake_collect)
    res = pipeline_tasks.step_collect(str(tmp_path), include_pending=True)
    assert [r["rec_idx"] for r in collect.read_targets(str(tmp_path))] == ["P1", "N1", "N2"]
    assert res == {"new": 2, "pending": 1, "excluded": 1}


def test_extract_passes_budget_and_alerts_once(monkeypatch, tmp_path):
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
    res = pipeline_tasks.step_extract(str(tmp_path), budget_usd=1.5, dag_label="매일 수집", limit=5.0)
    script, args = calls[0]
    assert script == "extract_skills.py" and "--tag=-ex" in args and args[args.index("--max-usd") + 1] == "1.5"
    assert len(sent) == 1 and "$5.00" in sent[0] and "$5.00" in sent[0] and "1건" in sent[0]
    assert res["stopped"] is True


def test_extract_with_no_budget_left_skips_llm(pt, tmp_path):
    write_rows(tmp_path, ["A", "B", "C"])
    res = pt.step_extract(str(tmp_path), budget_usd=0, dag_label="매일 수집", limit=5.0)
    assert pt._calls == [] and len(pt._sent) == 1 and "3건" in pt._sent[0]
    assert res["stopped"] is True


def test_summary_counts_results(tmp_path):
    import pipeline_tasks
    write_rows(tmp_path, ["A", "B", "C"])
    d = tmp_path / "out" / "extract" / "gpt-5.6-luna-ex"
    d.mkdir(parents=True)
    (d / "A.json").write_text(json.dumps({"cost_usd": 0.004, "review_reasons": []}), encoding="utf-8")
    (d / "B.json").write_text(json.dumps({"cost_usd": 0.0035, "review_reasons": [{"검사": 1, "내용": "x"}]}), encoding="utf-8")
    assert pipeline_tasks.summary(str(tmp_path)) == {"새 공고": 3, "추출": 2, "확인 필요": 1, "비용": 0.0075}


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
def test_pick_recheck_writes_check_file(monkeypatch, tmp_path):
    import datetime as dt
    import pipeline_tasks
    checked = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
    rows = [{"rec_idx": n, **ROW, "raw_hash": "h" * 64, "last_checked_at": checked} for n in ("A", "B")]
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "open_postings", lambda conn: rows)
    monkeypatch.setattr(pipeline_tasks.db_queries, "update_deadlines", lambda conn, m: len(m))
    monkeypatch.setattr(pipeline_tasks.collect, "scan_lists",
                        lambda **k: {"A": {"updated_at": checked + dt.timedelta(days=1), "deadline_text": ""}})
    res = pipeline_tasks.step_pick_recheck(str(tmp_path))
    check = json.loads((tmp_path / "check.json").read_text(encoding="utf-8"))
    assert [r["rec_idx"] for r in check] == ["A", "B"]          # A 수정, B 목록에 없음
    assert res == {"진행": 2, "수정": 1, "목록에 없음": 1, "마감일 바뀜": 0}


def test_detect_touches_unchanged_only(monkeypatch, tmp_path):
    import pipeline_tasks
    (tmp_path / "check.json").write_text(json.dumps([{"rec_idx": n, **ROW, "raw_hash": "h"} for n in "ABCD"]),
                                         encoding="utf-8")
    touched = []
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "touch_checked", lambda conn, nos: touched.extend(nos) or len(nos))
    monkeypatch.setattr(pipeline_tasks.recheck, "detect_changes",
                        lambda run_dir, rows: {"changed": ["B"], "closed": ["C"], "unchanged": ["A"], "error": ["D"]})
    res = pipeline_tasks.step_detect(str(tmp_path))
    assert touched == ["A"]          # 바뀐 공고는 다시 추출에 성공해야(DB 저장) 확인 시각이 바뀐다
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


def test_day_spent_counts_daily_and_recheck_only(tmp_path):
    """하루 상한은 ①+② 만(③ 은 따로 $10). 결과 파일의 run_at(UTC)을 KST 날짜로 센다 —
    DB 에 아직 안 들어간 결과(재시도·실패한 실행·같이 도는 실행)도 빠짐없이."""
    import datetime as dt
    import pipeline_tasks
    result(tmp_path, "daily_collect", "r1", "A", 1.0, "2026-10-28T03:00:00+00:00")     # KST 10/28 12:00
    result(tmp_path, "recheck_postings", "r2", "B", 0.5, "2026-10-27T16:00:00+00:00")  # KST 10/28 01:00
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


def test_collect_defers_excluded_until_load(monkeypatch, tmp_path):
    """버린 공고는 수집 때가 아니라 DB 저장에 성공한 뒤 기록한다 — 실패한 ① 의 버린 공고가 다음 날 '아는 번호'로
    연속 5개 멈춤을 일으켜 그날 공고를 놓치지 않게."""
    import collect
    import pipeline_tasks
    got = {}
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "known_posting_nos", lambda conn: set())
    monkeypatch.setattr(pipeline_tasks.db_queries, "pending_postings", lambda conn: [])
    monkeypatch.setattr(pipeline_tasks.db_queries, "record_excluded", lambda conn, rows: pytest.fail("수집 때 기록함"))

    def fake_collect(run_dir, known, **k):
        got.update(k)
        collect.write_targets(run_dir, [])
        return {"targets": [], "excluded": [("X9", "4년 이상")], "listed": 1, "stopped": {}}

    monkeypatch.setattr(pipeline_tasks.collect, "collect_list", fake_collect)
    assert pipeline_tasks.step_collect(str(tmp_path), include_pending=False)["excluded"] == 1
    assert json.loads((tmp_path / "excluded.json").read_text(encoding="utf-8")) == [["X9", "4년 이상"]]
    assert got["stop_after"] is None                  # ③: 연속 멈춤 없이 목록 끝까지(아는 번호는 건너뜀)
    pipeline_tasks.step_collect(str(tmp_path / "d"), include_pending=True)
    assert got["stop_after"] == 5                     # ①: 연속 5개 멈춤


def test_load_records_excluded_after_saving(monkeypatch, tmp_path):
    import pipeline_tasks
    order = []
    monkeypatch.setattr(pipeline_tasks, "run_script", lambda script, args, run_dir, **k: order.append(script))
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "record_excluded",
                        lambda conn, rows: order.append(("버린 공고", [tuple(r) for r in rows])) or len(rows))
    write_rows(tmp_path, ["A"])
    (tmp_path / "excluded.json").write_text('[["X9", "4년 이상"]]', encoding="utf-8")
    pipeline_tasks.step_load(str(tmp_path))
    assert order == ["db_load.py", ("버린 공고", [("X9", "4년 이상")])]
    order.clear()
    write_rows(tmp_path, [])                         # 새 공고 0건이어도 버린 공고는 기록
    pipeline_tasks.step_load(str(tmp_path))
    assert order == [("버린 공고", [("X9", "4년 이상")])]


def test_pick_recheck_updates_deadlines_from_list(monkeypatch, tmp_path):
    """목록의 마감일로 DB 마감일을 바꾼다 — 고른 공고만이 아니라 목록에 보이는 공고 전부(요청 추가 없음)."""
    import datetime as dt
    import pipeline_tasks
    checked = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
    rows = [{"rec_idx": "A", **ROW, "raw_hash": "h", "last_checked_at": checked}]
    got = {}
    monkeypatch.setattr(pipeline_tasks, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(pipeline_tasks.db_queries, "open_postings", lambda conn: rows)
    monkeypatch.setattr(pipeline_tasks.db_queries, "today_kst", lambda: dt.date(2026, 10, 28))
    monkeypatch.setattr(pipeline_tasks.db_queries, "update_deadlines", lambda conn, m: got.update(m) or 1)
    monkeypatch.setattr(pipeline_tasks.collect, "scan_lists", lambda **k: {
        "A": {"updated_at": None, "deadline_text": "~11.30(월)"},          # 등록만(본문 확인 안 함)이어도 마감일은 반영
        "N": {"updated_at": None, "deadline_text": "상시채용"}})            # 읽을 수 없는 마감일은 넘기지 않음
    res = pipeline_tasks.step_pick_recheck(str(tmp_path))
    assert got == {"A": dt.date(2026, 11, 30)}
    assert res["마감일 바뀜"] == 1
