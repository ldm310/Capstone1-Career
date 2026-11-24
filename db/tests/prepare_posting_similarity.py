"""Initialize ONLY a new, empty local extcrawler_test_similarity_* database.

Connection values come from POSTING_SIMILARITY_TEST_DSN, never a team env file.
This is synthetic test preparation, not a migration or existing DB cleanup tool.
"""
import os
import re
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[2]


def prepare():
    dsn = os.environ.get('POSTING_SIMILARITY_TEST_DSN', '')
    config = conninfo_to_dict(dsn)
    if (config.get('host') not in ('127.0.0.1', 'localhost')
            or config.get('hostaddr', '127.0.0.1') != '127.0.0.1'
            or not re.fullmatch(r'extcrawler_test_similarity_[a-z0-9]+', config.get('dbname', ''))
            or any(key in config for key in ('service', 'options'))):
        raise ValueError('An explicit isolated loopback similarity test database is required')
    with psycopg.connect(dsn, connect_timeout=10, autocommit=True) as conn:
        if conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')").fetchone()[0]:
            raise ValueError('Test database must be empty; existing databases are never reset')
        conn.execute((ROOT / 'db/init/01-job-schema.sql').read_text(encoding='utf-8'))
        with conn.transaction():
            conn.execute((ROOT / 'backend/src/test/resources/posting-similarity-fixtures.sql').read_text(encoding='utf-8'))


if __name__ == '__main__':
    try:
        prepare()
        print('Isolated PostgreSQL similarity fixtures prepared')
    except Exception as error:
        # Never echo a DSN, server message, username or password.
        print('Similarity fixture preparation failed: ' + type(error).__name__)
        raise SystemExit(1)
