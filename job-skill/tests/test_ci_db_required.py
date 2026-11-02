"""CI 에서는 DB 가 없으면 DB 시험을 건너뛰지 말고 실패해야 한다(REQUIRE_DB=1). 노트북에서는 지금처럼 건너뛴다."""
from __future__ import annotations

import os
import subprocess
import sys

from conftest import HERE

NO_DB = "postgresql://nobody:x@127.0.0.1:1/none"   # 아무도 듣지 않는 곳


def _run(require: bool) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": NO_DB, "TEST_DATABASE_URL": NO_DB, "PYTHONIOENCODING": "utf-8"}
    env.pop("REQUIRE_DB", None)
    if require:
        env["REQUIRE_DB"] = "1"
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "tests/test_dictionary_db.py::test_exclude_word_kind_is_checked"],
                          cwd=HERE, env=env, capture_output=True, text=True, encoding="utf-8")


def test_without_db_is_skipped_on_laptop():
    r = _run(require=False)
    assert r.returncode == 0 and "1 skipped" in r.stdout


def test_without_db_fails_in_ci():
    r = _run(require=True)
    assert r.returncode != 0 and "1 error" in r.stdout
