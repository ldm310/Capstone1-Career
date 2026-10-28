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
    monkeypatch.setattr(pipeline_tasks, "run_script", lambda script, args, run_dir: calls.append((script, list(args))))
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


def test_ocr_always_uses_gpu(pt, tmp_path):
    write_rows(tmp_path, ["A"])
    with_image(tmp_path)
    pt.step_ocr(str(tmp_path))
    assert pt._calls == [("dump_paddle_boxes.py", ["--gpu"])]


def test_ocr_failure_propagates(monkeypatch, tmp_path):
    import pipeline_tasks
    write_rows(tmp_path, ["A"])
    with_image(tmp_path)

    def boom(script, args, run_dir):
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
