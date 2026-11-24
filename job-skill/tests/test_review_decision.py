"""사람 검토(정상·제외·다시) — 2026-11-24 사용자 결정.
관리자 페이지에서 추출 결과를 보고 정상(결과 맞음)·제외(앞으로 자동 처리·웹에서 뺌)·다시(피드백을 붙여 다음 ① 때 다시 추출)를 고른다.
값은 extraction_run 의 review_result·review_feedback·reviewed_at 에 쓰고, 팀원(웹) 계정은 이 세 칸만 쓸 수 있다."""
from __future__ import annotations

import os

import psycopg
import pytest

from conftest import HERE
from test_db_queries import add_posting, add_run

MIGRATION_010 = os.path.join(HERE, "db", "migrations", "010_review_decision.sql")


def review(conn, run_id, result, feedback=None):
    conn.execute("UPDATE extraction_run SET review_result = %s, review_feedback = %s, reviewed_at = now() WHERE id = %s",
                 (result, feedback, run_id))


def test_review_values_and_feedback_rule(db):
    """값은 정상·제외·다시만. '다시'는 피드백이 꼭 있어야 하고(빈칸만이면 안 됨), 결과와 시각은 함께."""
    run = add_run(db, add_posting(db, "1"))
    for result, fb in (("다시", None), ("다시", "  "), ("문제없음", None)):
        with pytest.raises(psycopg.errors.CheckViolation):
            review(db, run, result, fb)
    with pytest.raises(psycopg.errors.CheckViolation):          # 결과만 있고 시각 없음
        db.execute("UPDATE extraction_run SET review_result = '정상' WHERE id = %s", (run,))
    for result, fb in (("정상", None), ("제외", None), ("다시", "자리를 하나로")):
        review(db, run, result, fb)


def test_migration_010_converts_old_db_and_is_repeatable(db):
    """이미 있는 DB(RDS): 옛 값(문제없음·고침)은 정상으로, 피드백 칸을 더한다. 두 번 돌려도 같다."""
    db.execute("ALTER TABLE extraction_run DROP COLUMN review_feedback, DROP CONSTRAINT extraction_run_review_result_check")
    db.execute("""ALTER TABLE extraction_run ADD CONSTRAINT extraction_run_review_result_check
                  CHECK (review_result IN ('문제없음', '고침'))""")
    run = add_run(db, add_posting(db, "1"))
    db.execute("UPDATE extraction_run SET review_result = '고침', reviewed_at = now() WHERE id = %s", (run,))
    sql = open(MIGRATION_010, encoding="utf-8").read()
    db.execute(sql)
    db.execute(sql)
    assert db.execute("SELECT review_result FROM extraction_run WHERE id = %s", (run,)).fetchone()[0] == "정상"
    review(db, run, "다시", "피드백")                               # 새 칸·새 값이 된다


def test_team_can_write_only_review_columns(db):
    """팀원 역할 team: 읽기 권한은 그대로, 검토 칸 세 개만 쓸 수 있다."""
    db.execute("""DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'team') THEN CREATE ROLE team NOLOGIN; END IF;
                  END $$""")
    db.execute("GRANT SELECT ON extraction_run TO team")             # RDS 와 같은 읽기 권한
    db.execute(open(MIGRATION_010, encoding="utf-8").read())
    run = add_run(db, add_posting(db, "1"))
    db.execute("SET ROLE team")
    try:
        review(db, run, "다시", "자리를 하나로")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute("UPDATE extraction_run SET is_current = false WHERE id = %s", (run,))
    finally:
        db.execute("RESET ROLE")
