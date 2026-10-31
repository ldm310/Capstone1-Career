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
