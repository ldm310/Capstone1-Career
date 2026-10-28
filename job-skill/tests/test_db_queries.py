"""db_queries(파이프라인용 조회)와 db_load 의 원본 갱신 규칙 시험."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

import pytest

from conftest import HERE

KST = dt.timezone(dt.timedelta(hours=9))
TODAY = dt.datetime.now(KST).date()


def add_posting(conn, no, status="진행", deadline=None, raw_hash="a" * 64, title="지어낸 공고"):
    cid = conn.execute("""INSERT INTO company (name) VALUES ('(주)지어낸회사')
                          ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id""").fetchone()[0]
    return conn.execute(
        """INSERT INTO posting (company_id, site_posting_no, title, site_job_category, career_condition, kind,
                                status, deadline, raw_path, raw_hash)
           VALUES (%s, %s, %s, '백엔드', '신입 · 경력', '글', %s, %s, 'x.html', %s) RETURNING id""",
        (cid, no, title, status, deadline, raw_hash)).fetchone()[0]


def add_run(conn, posting_id, run_at=None, cost=0.0, current=True):
    return conn.execute(
        """INSERT INTO extraction_run (posting_id, model, prompt_version, dict_version, input_hash, input_tokens,
                                       output_tokens, cost_usd, is_current, run_at)
           VALUES (%s, 'gpt-5.6-luna', 'v', '0.1.1', %s, 1, 1, %s, %s, coalesce(%s, now())) RETURNING id""",
        (posting_id, "b" * 64, cost, current, run_at)).fetchone()[0]


def test_known_includes_postings_and_excluded(db):
    import db_queries as q
    add_posting(db, "100")
    assert q.record_excluded(db, [("200", "4년 이상")]) == 1
    assert q.known_posting_nos(db) == {"100", "200"}
    assert q.record_excluded(db, [("200", "4년 이상")]) == 0


def test_open_postings_hides_past_deadline(db):
    import db_queries as q
    add_posting(db, "1", deadline=TODAY - dt.timedelta(days=1))
    add_posting(db, "2", deadline=TODAY)
    add_posting(db, "3", deadline=None)
    add_posting(db, "4", status="마감", deadline=TODAY + dt.timedelta(days=5))
    rows = q.open_postings(db)
    assert sorted(r["rec_idx"] for r in rows) == ["2", "3"]
    assert {"raw_hash", "company", "title", "role", "career", "deadline"} <= set(rows[0])


def test_pending_is_open_without_run(db):
    import db_queries as q
    add_posting(db, "30")                                         # A: 실행 없음 → pending
    b = add_posting(db, "10")
    add_run(db, b)                                                # B: 실행 있음 → 아님
    add_posting(db, "20", deadline=TODAY - dt.timedelta(days=1))  # C: 마감일 지남 → 아님
    add_posting(db, "5")                                          # A2: 실행 없음 → pending
    rows = q.pending_postings(db)
    assert [r["rec_idx"] for r in rows] == ["5", "30"]
    assert rows[0]["kind"] == "" and rows[0]["text_chars"] == "" and rows[0]["images"] == ""
    assert rows[0]["role"] == "백엔드" and rows[0]["career"] == "신입 · 경력"


def test_day_cost_uses_kst_boundaries(db):
    import db_queries as q
    p = add_posting(db, "1")
    add_run(db, p, run_at=dt.datetime(2026, 10, 27, 23, 30, tzinfo=KST), cost=0.10, current=False)
    add_run(db, p, run_at=dt.datetime(2026, 10, 28, 0, 10, tzinfo=KST), cost=0.20)
    usd, n = q.day_cost(db, dt.date(2026, 10, 27))
    assert (round(usd, 6), n) == (0.10, 1)


def test_mark_closed_and_touch(db):
    import db_queries as q
    add_posting(db, "A")
    add_posting(db, "B")
    before = db.execute("SELECT last_checked_at FROM posting WHERE site_posting_no = 'B'").fetchone()[0]
    assert q.mark_closed(db, ["A"]) == 1
    assert [r["rec_idx"] for r in q.open_postings(db)] == ["B"]
    assert q.touch_checked(db, ["B"]) == 1
    after = db.execute("SELECT last_checked_at FROM posting WHERE site_posting_no = 'B'").fetchone()[0]
    assert after > before


def _write_run(run_dir, page_text):
    os.makedirs(os.path.join(run_dir, "pages"), exist_ok=True)
    with open(os.path.join(run_dir, "targets.tsv"), "w", encoding="utf-8") as f:
        f.write("rec_idx\tcompany\ttitle\trole\tcareer\tdeadline\tkind\ttext_chars\timages\n")
        f.write("D\t(주)지어낸회사\t지어낸 공고\t백엔드\t신입 · 경력\t\t글\t300\t0\n")
    with open(os.path.join(run_dir, "pages", "D.html"), "w", encoding="utf-8") as f:
        f.write(f'<html><div class="user_content"><p>{page_text}</p></div><script></script></html>')


def _load(run_dir, db_url):
    env = {**os.environ, "OCR_DATA_DIR": str(run_dir), "DATABASE_URL": db_url, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "db_load.py", "load", "--run", "gpt-5.6-luna-ex"], cwd=HERE, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr


def test_load_keeps_old_raw_when_not_extracted(db, db_url, tmp_path):
    import db_load
    add_posting(db, "D", raw_hash="0" * 64)
    _write_run(tmp_path, "새로 바뀐 공고 본문 내용입니다")
    _load(tmp_path, db_url)                       # 추출 결과 없음 → 원본 그대로
    assert db.execute("SELECT raw_hash FROM posting WHERE site_posting_no='D'").fetchone()[0] == "0" * 64

    res = tmp_path / "out" / "extract" / "gpt-5.6-luna-ex"
    res.mkdir(parents=True)
    (res / "D.json").write_text(json.dumps({"rec_idx": "D", "model": "gpt-5.6-luna", "input_tokens": 10,
                                            "output_tokens": 5, "positions": []}), encoding="utf-8")
    _load(tmp_path, db_url)                       # 추출 결과 있음 → 원본 갱신
    page = (tmp_path / "pages" / "D.html").read_text(encoding="utf-8")
    assert db.execute("SELECT raw_hash FROM posting WHERE site_posting_no='D'").fetchone()[0] == db_load.content_hash(page, "D")


def test_open_postings_has_last_checked_at(db):
    import db_queries as q
    add_posting(db, "A")
    assert isinstance(q.open_postings(db)[0]["last_checked_at"], dt.datetime)


def test_load_moves_last_checked_only_when_extracted(db, db_url, tmp_path):
    """다시 추출에 실패한 공고는 마지막 확인 시각도 그대로 → 다음 ② 가 '수정'으로 다시 잡는다."""
    old = dt.datetime(2026, 10, 1, 12, 0, tzinfo=KST)
    add_posting(db, "D", raw_hash="0" * 64)
    db.execute("UPDATE posting SET last_checked_at = %s WHERE site_posting_no = 'D'", (old,))
    _write_run(tmp_path, "새로 바뀐 공고 본문 내용입니다")
    _load(tmp_path, db_url)                       # 추출 결과 없음
    assert db.execute("SELECT last_checked_at FROM posting WHERE site_posting_no='D'").fetchone()[0] == old

    res = tmp_path / "out" / "extract" / "gpt-5.6-luna-ex"
    res.mkdir(parents=True)
    (res / "D.json").write_text(json.dumps({"rec_idx": "D", "model": "gpt-5.6-luna", "input_tokens": 10,
                                            "output_tokens": 5, "positions": []}), encoding="utf-8")
    _load(tmp_path, db_url)                       # 추출 결과 있음
    assert db.execute("SELECT last_checked_at FROM posting WHERE site_posting_no='D'").fetchone()[0] > old
