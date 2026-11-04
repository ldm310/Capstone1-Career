"""AWS 브랜치: 파이프라인은 RDS 로, 시험은 늘 로컬 Docker DB 로(시험이 RDS 에 임시 DB 를 만들지 않게)."""
from __future__ import annotations

import pytest


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """db_load 가 읽는 .env 를 지어낸 값으로 바꾼다."""
    import db_load
    monkeypatch.setattr(db_load, "HERE", str(tmp_path))
    for k in ("DATABASE_URL", "TEST_DATABASE_URL", "RDS_HOST", "RDS_PASSWORD"):
        monkeypatch.delenv(k, raising=False)

    def write(**kv):
        (tmp_path / ".env").write_text("".join(f"{k}={v}\n" for k, v in kv.items()), encoding="utf-8")
    return write


LOCAL = "postgresql://career:local@localhost:5433/career"


def test_pipeline_uses_rds_when_set(env_file):
    import db_load
    env_file(DATABASE_URL=LOCAL, RDS_HOST="db.example.ap-northeast-2.rds.amazonaws.com", RDS_PASSWORD="p@ss:w/rd")
    assert db_load.database_url() == \
        "postgresql://career:p%40ss%3Aw%2Frd@db.example.ap-northeast-2.rds.amazonaws.com:5432/career?sslmode=require"


def test_explicit_database_url_wins(env_file, monkeypatch):
    """DATABASE_URL 환경변수를 직접 준 경우(시험의 임시 DB 등)는 그것을 쓴다 — 시험 공고가 RDS 에 들어가지 않게."""
    import db_load
    env_file(RDS_HOST="db.example", RDS_PASSWORD="x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://career:x@localhost:5433/job_test_1")
    assert db_load.database_url() == "postgresql://career:x@localhost:5433/job_test_1"


def test_empty_database_url_env_falls_back_to_rds(env_file, monkeypatch):
    """Airflow 컨테이너는 DATABASE_URL 을 빈 값으로 덮어 RDS 를 쓰게 한다(.env 의 로컬 주소가 컨테이너로 넘어가도)."""
    import db_load
    env_file(DATABASE_URL=LOCAL, RDS_HOST="db.example", RDS_PASSWORD="x")
    monkeypatch.setenv("DATABASE_URL", "")
    assert db_load.database_url().startswith("postgresql://career:x@db.example:5432/career")


def test_without_rds_uses_local(env_file):
    import db_load
    env_file(DATABASE_URL=LOCAL)
    assert db_load.database_url() == LOCAL


def test_tests_always_use_local_db(env_file, monkeypatch):
    import db_load
    env_file(DATABASE_URL=LOCAL, RDS_HOST="db.example", RDS_PASSWORD="x")
    assert db_load.local_database_url() == LOCAL
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://career:y@host.docker.internal:5433/career")
    assert db_load.local_database_url() == "postgresql://career:y@host.docker.internal:5433/career"
