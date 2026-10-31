"""표준화 사전 표(DB 가 원본) — 변경 기록 트리거, 대표 능력, 스킬이 아닌 낱말. 시드에 없는 '시험…' 이름만 쓴다."""
from __future__ import annotations

import psycopg
import pytest


def test_change_is_logged_with_session_user(db):
    db.execute("INSERT INTO tech (name) VALUES ('시험기술')")
    db.execute("UPDATE tech SET aliases = '{시험}' WHERE name = '시험기술'")
    db.execute("DELETE FROM tech WHERE name = '시험기술'")
    rows = db.execute("""SELECT action, changed_by, old_row->>'name', new_row->'aliases'
                         FROM dictionary_change
                         WHERE table_name = 'tech' AND coalesce(new_row, old_row)->>'name' = '시험기술'
                         ORDER BY id""").fetchall()
    user = db.execute("SELECT session_user").fetchone()[0]
    assert [r[0] for r in rows] == ["넣기", "고치기", "지우기"]
    assert {r[1] for r in rows} == {user}
    assert rows[1][3] == ["시험"] and rows[2][2] == "시험기술"


def test_noop_update_not_logged(db):
    db.execute("INSERT INTO capability (name) VALUES ('시험능력')")
    db.execute("UPDATE capability SET aliases = aliases WHERE name = '시험능력'")
    assert db.execute("""SELECT count(*) FROM dictionary_change
                         WHERE action = '고치기' AND new_row->>'name' = '시험능력'""").fetchone()[0] == 0


def test_truncate_is_blocked(db):
    with pytest.raises(psycopg.errors.RaiseException, match="TRUNCATE"):
        db.execute("TRUNCATE exclude_word")


def test_one_primary_per_tech(db):
    t = db.execute("INSERT INTO tech (name) VALUES ('시험기술') RETURNING id").fetchone()[0]
    c1 = db.execute("INSERT INTO capability (name) VALUES ('시험능력1') RETURNING id").fetchone()[0]
    c2 = db.execute("INSERT INTO capability (name) VALUES ('시험능력2') RETURNING id").fetchone()[0]
    db.execute("INSERT INTO tech_capability (tech_id, capability_id, is_primary) VALUES (%s, %s, true)", (t, c1))
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute("INSERT INTO tech_capability (tech_id, capability_id, is_primary) VALUES (%s, %s, true)", (t, c2))


def test_exclude_word_kind_is_checked(db):
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("INSERT INTO exclude_word (word, kind) VALUES ('x', '모름')")


# ---------------------------------------------------------------- 시드(빈 DB 채우기)·내려받기

def test_seed_fills_empty_db(db):          # conftest 가 시드를 적용한 임시 DB
    assert db.execute("SELECT count(*) FROM capability WHERE name <> '기타'").fetchone()[0] == 61
    assert db.execute("SELECT count(*) FROM tech").fetchone()[0] == 184
    assert db.execute("SELECT count(*) FROM exclude_word").fetchone()[0] == 61
    rds = db.execute("""SELECT c.name FROM tech_capability tc JOIN tech t ON t.id = tc.tech_id
                        JOIN capability c ON c.id = tc.capability_id WHERE t.name = 'RDS' AND tc.is_primary""").fetchone()
    assert rds == ("클라우드",)            # JSON 의 첫 번째 능력이 대표


def test_seed_does_nothing_when_dictionary_exists(db):
    import db_load
    db.execute("DELETE FROM exclude_word WHERE word = 'CTO'")
    db.execute(open(db_load.SEED_SQL, encoding="utf-8").read())
    assert db.execute("SELECT count(*) FROM exclude_word WHERE word = 'CTO'").fetchone()[0] == 0


def test_export_round_trip_is_identical(db):
    import db_load
    assert db_load.export_dictionary(db) == open(db_load.SEED_SQL, encoding="utf-8").read()


def test_saved_run_records_dictionary_version(db, tmp_path):
    """추출 결과를 저장하면 그 결과가 쓴 사전 판(지문)이 dictionary_version 에 한 줄 남는다(같은 판은 한 줄)."""
    import db_load
    from test_db_queries import add_posting
    path = tmp_path / "A.json"
    path.write_text("{}", encoding="utf-8")
    run = {"model": "gpt-5.6-luna", "prompt_version": "p" * 12, "dict_version": "abcdef123456", "input_hash": "1" * 64,
           "input_tokens": 10, "output_tokens": 5, "positions": []}
    for no, ih in (("A", "1" * 64), ("B", "2" * 64)):
        db_load.insert_run(db, add_posting(db, no), {**run, "input_hash": ih}, None, str(path), {}, {})
    assert db.execute("SELECT version FROM dictionary_version").fetchall() == [("abcdef123456",)]
