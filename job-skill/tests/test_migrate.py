"""db_load.migrate — 아직 적용하지 않은 마이그레이션만 번호 순서대로 적용하고 schema_migration 에 기록한다.
CD 가 main 에 합칠 때마다 RDS 에 부르므로 몇 번 돌려도 같은 결과여야 한다(멱등)."""
from __future__ import annotations

import glob
import os
import secrets

import psycopg
import pytest

from conftest import HERE, _no_db, _with_db

REAL = sorted(os.path.basename(p) for p in glob.glob(os.path.join(HERE, "db", "migrations", "*.sql")))


@pytest.fixture
def empty_db_url():
    """빈 임시 DB(표 없음)."""
    import db_load
    admin = db_load.local_database_url()
    if not admin:
        _no_db("DATABASE_URL 없음")
    name = "job_test_" + secrets.token_hex(4)
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as c:
            c.execute(f'CREATE DATABASE "{name}"')
    except psycopg.OperationalError as e:
        _no_db(f"career-db 에 접속할 수 없음: {e}")
    yield _with_db(admin, name)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_migrate_applies_only_new_files(empty_db_url, tmp_path, monkeypatch):
    import db_load
    monkeypatch.setattr(db_load, "MIGRATIONS_DIR", str(tmp_path))
    (tmp_path / "001_a.sql").write_text("CREATE TABLE hits (name text); INSERT INTO hits VALUES ('001');", encoding="utf-8")
    (tmp_path / "002_b.sql").write_text("INSERT INTO hits VALUES ('002');", encoding="utf-8")
    with psycopg.connect(empty_db_url, autocommit=True) as c:
        assert db_load.migrate(c) == ["001_a.sql", "002_b.sql"]
        assert db_load.migrate(c) == []                                   # 다시 돌려도 아무것도 안 함
        (tmp_path / "003_c.sql").write_text("INSERT INTO hits VALUES ('003');", encoding="utf-8")
        assert db_load.migrate(c) == ["003_c.sql"]
        assert [r[0] for r in c.execute("SELECT name FROM hits ORDER BY name")] == ["001", "002", "003"]


def test_failed_migration_is_not_recorded(empty_db_url, tmp_path, monkeypatch):
    """중간에 실패하면 거기서 멈추고(기록 안 함), 고친 뒤 다시 돌리면 실패한 것부터 이어서 한다."""
    import db_load
    monkeypatch.setattr(db_load, "MIGRATIONS_DIR", str(tmp_path))
    (tmp_path / "001_a.sql").write_text("CREATE TABLE hits (name text);", encoding="utf-8")
    (tmp_path / "002_b.sql").write_text("BEGIN; INSERT INTO nope VALUES (1); COMMIT;", encoding="utf-8")
    with psycopg.connect(empty_db_url, autocommit=True) as c:
        with pytest.raises(psycopg.errors.UndefinedTable):
            db_load.migrate(c)
        (tmp_path / "002_b.sql").write_text("BEGIN; INSERT INTO hits VALUES ('002'); COMMIT;", encoding="utf-8")
        assert db_load.migrate(c) == ["002_b.sql"]
        assert [r[0] for r in c.execute("SELECT name FROM schema_migration ORDER BY name")] == ["001_a.sql", "002_b.sql"]


def test_init_records_migrations_as_applied(empty_db_url, monkeypatch):
    """새 DB(init: schema.sql + 시드)는 이미 최신 구조라, 지금 있는 마이그레이션을 적용한 것으로 기록한다."""
    import db_load
    monkeypatch.setenv("DATABASE_URL", empty_db_url)
    db_load.cmd_init()
    with psycopg.connect(empty_db_url, autocommit=True) as c:
        assert [r[0] for r in c.execute("SELECT name FROM schema_migration ORDER BY name")] == REAL
        assert db_load.migrate(c) == []


def test_real_migrations_rerun_safely_on_existing_db(db_url):
    """지금 RDS 처럼 마이그레이션은 적용됐지만 기록이 없는 DB: 처음 migrate 는 모두 다시 적용(모두 여러 번 안전)하고 기록한다."""
    import db_load
    with psycopg.connect(db_url, autocommit=True) as c:
        before = c.execute("SELECT count(*) FROM posting").fetchone()[0], c.execute("SELECT count(*) FROM tech").fetchone()[0]
        assert db_load.migrate(c) == REAL
        assert db_load.migrate(c) == []
        assert (c.execute("SELECT count(*) FROM posting").fetchone()[0], c.execute("SELECT count(*) FROM tech").fetchone()[0]) == before
