"""db_load.load — 저장 중 트랜잭션 실패: 일시 오류는 공고마다 다시 하고, 다시 해도 같은 오류인 공고는 건너뛰고 알린다.
지어낸 공고, career-db 의 임시 DB 에 넣는다."""
from __future__ import annotations

import csv
import os

import psycopg
import pytest

FIELDS = ["rec_idx", "company", "title", "role", "career", "deadline", "kind", "text_chars", "images"]


@pytest.fixture
def run(tmp_path, monkeypatch, db_url):
    """지어낸 공고 D·E 의 실행 폴더를 만들고, db_load 가 그 폴더와 임시 DB 를 보게 한다."""
    import db_load
    pages = tmp_path / "pages"
    pages.mkdir()
    rows = []
    for no in ("D", "E"):
        (pages / f"{no}.html").write_text(
            f'<html><div class="user_content"><p>지어낸 공고 {no} 본문입니다</p></div><script></script></html>', encoding="utf-8")
        rows.append({"rec_idx": no, "company": "(주)지어낸회사", "title": f"지어낸 공고 {no}", "role": "백엔드",
                     "career": "신입", "deadline": "", "kind": "글", "text_chars": "300", "images": "0"})
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setattr(db_load, "PAGE_DIR", str(pages))
    monkeypatch.setattr(db_load, "EX", str(tmp_path / "out" / "extract"))
    monkeypatch.setattr(db_load, "load_targets", lambda: rows)
    monkeypatch.setattr(db_load, "image_rows", lambda: {})
    monkeypatch.setattr(db_load, "kept_by_image", lambda: {})
    monkeypatch.setattr(db_load, "RETRY_WAIT", 0)
    return db_load


def flaky_upsert(db_load, monkeypatch, fail):
    """fail(공고번호, 몇 번째 시도) 가 예외를 주면 그 시도에서 던진다. 시도 수를 센다."""
    real, tries = db_load.upsert_posting, {}

    def upsert(conn, t, update_raw=True):
        no = t["rec_idx"]
        tries[no] = tries.get(no, 0) + 1
        if (e := fail(no, tries[no])) is not None:
            raise e
        return real(conn, t, update_raw)

    monkeypatch.setattr(db_load, "upsert_posting", upsert)
    return tries


def saved(db):
    return sorted(r[0] for r in db.execute("SELECT site_posting_no FROM posting").fetchall())


def test_transient_error_is_retried(run, monkeypatch, db):
    tries = flaky_upsert(run, monkeypatch, lambda no, k: psycopg.OperationalError("지어낸 연결 끊김") if no == "D" and k == 1 else None)
    total, failed = run.load("gpt-5.6-luna-ex")
    assert failed == [] and tries["D"] == 2 and total["공고"] == 2      # 두 번째 시도에 저장, 공고 수는 한 번만 셈
    assert saved(db) == ["D", "E"]


def test_gives_up_after_three_transient_errors(run, monkeypatch, db):
    tries = flaky_upsert(run, monkeypatch, lambda no, k: psycopg.OperationalError("지어낸 연결 끊김") if no == "D" else None)
    total, failed = run.load("gpt-5.6-luna-ex")
    assert failed == ["D"] and tries["D"] == 3 and total["저장 실패"] == 1
    assert saved(db) == ["E"]                                           # 뒤 공고는 그대로 저장


def test_permanent_error_skips_only_that_posting(run, monkeypatch, db):
    tries = flaky_upsert(run, monkeypatch, lambda no, k: ValueError("지어낸 데이터 오류") if no == "D" else None)
    total, failed = run.load("gpt-5.6-luna-ex")
    assert failed == ["D"] and tries["D"] == 1                          # 다시 해도 같은 오류라 다시 하지 않음
    assert saved(db) == ["E"]


def test_cmd_load_writes_result_and_fails(run, monkeypatch, tmp_path):
    import json
    flaky_upsert(run, monkeypatch, lambda no, k: ValueError("지어낸 데이터 오류") if no == "D" else None)
    monkeypatch.setattr(run, "OUT_DIR", str(tmp_path / "out"))
    with pytest.raises(SystemExit) as e:
        run.cmd_load("gpt-5.6-luna-ex")
    assert e.value.code == 1
    res = json.loads((tmp_path / "out" / "load_result.json").read_text(encoding="utf-8"))
    assert res["failed"] == ["D"] and res["total"]["공고"] == 1
