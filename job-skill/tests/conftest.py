"""시험 공용 도구. DB 시험은 career-db 안에 임시 DB(job_test_*)를 만들어 쓰고 끝나면 지운다."""
from __future__ import annotations

import glob
import os
import secrets
import sys
import urllib.parse

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # job-skill/
if HERE not in sys.path:
    sys.path.insert(0, HERE)


@pytest.fixture(autouse=True)
def no_real_slack(monkeypatch, tmp_path_factory):
    """시험이 진짜 Slack 채널로 보내지 않게: 웹훅 주소를 지운다(.env·환경변수 모두). 보내기 시험은 스스로 다시 넣는다."""
    import notify
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(notify, "ENV_PATH", str(tmp_path_factory.mktemp("noenv") / ".env"))


def _with_db(url: str, name: str) -> str:
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, "/" + name, p.query, p.fragment))


@pytest.fixture
def db_url():
    """임시 DB 를 만들고 스키마·마이그레이션을 적용한 뒤 접속 주소를 준다."""
    import psycopg
    import db_load

    admin = db_load.local_database_url()   # 시험은 늘 로컬 Docker DB 에(RDS 에 임시 DB 를 만들지 않게)
    if not admin:
        pytest.skip("DATABASE_URL 없음")
    name = "job_test_" + secrets.token_hex(4)
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as c:
            c.execute(f'CREATE DATABASE "{name}"')
    except psycopg.OperationalError as e:
        pytest.skip(f"career-db 에 접속할 수 없음: {e}")
    url = _with_db(admin, name)
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(open(os.path.join(HERE, "db", "schema.sql"), encoding="utf-8").read())
        for path in sorted(glob.glob(os.path.join(HERE, "db", "migrations", "*.sql"))):
            c.execute(open(path, encoding="utf-8").read())
    yield url
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def db(db_url):
    """임시 DB 연결(search_path=job, autocommit)."""
    import psycopg

    with psycopg.connect(db_url, autocommit=True, options="-c search_path=job") as c:
        yield c
