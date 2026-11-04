"""deploy_airflow — CD 가 노트북 Airflow 전용 폴더를 main 의 커밋으로 바꾼다. 같은 커밋으로 다시 돌려도 아무 일 없음(멱등).
git·docker 는 가짜(명령만 기록)."""
from __future__ import annotations

import subprocess

import pytest

import deploy_airflow as d


class Fake:
    """가짜 명령 실행: HEAD 커밋, 바뀐 파일, 도는 DAG 실행 수를 정해 두고 부른 명령을 기록한다."""

    def __init__(self, head="aaa", changed=(), running=(0,)):
        self.head, self.changed, self.running, self.calls = head, list(changed), list(running), []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if "list-runs" in cmd:
            if "daily_collect" not in cmd:                     # 도는 실행은 매일 수집에만 있다고 둠
                return "[]"
            n = self.running.pop(0) if len(self.running) > 1 else self.running[0]
            return "[" + ",".join(["{}"] * n) + "]"
        if cmd[-2:] == ["rev-parse", "HEAD"]:
            return self.head + "\n"
        if "diff" in cmd:                                       # git 처럼 '--' 뒤에 적은 파일만
            wanted = cmd[cmd.index("--") + 1:]
            return "\n".join(f for f in self.changed if f in wanted)
        if "checkout" in cmd:
            self.head = cmd[-1]
        return ""

    def did(self, word):
        return [c for c in self.calls if word in c]


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".git").mkdir()
    return str(tmp_path)


def test_same_commit_changes_nothing(repo):
    run = Fake(head="aaa")
    out = d.deploy(repo, "aaa", run=run, sleep=lambda s: None)
    assert out == {"from": "aaa", "to": "aaa", "changed": False, "rebuilt": False}
    assert not run.did("checkout") and not run.did("build") and run.did("up")   # up -d 는 이미 떠 있으면 그대로


def test_code_change_checks_out_without_rebuild(repo):
    run = Fake(head="aaa", changed=["job-skill/recheck.py"])
    out = d.deploy(repo, "bbb", run=run, sleep=lambda s: None)
    assert out["changed"] and not out["rebuilt"] and run.did("checkout")[0][-1] == "bbb"


def test_image_change_rebuilds(repo):
    run = Fake(head="aaa", changed=["job-skill/airflow/requirements-airflow.txt"])
    assert d.deploy(repo, "bbb", run=run, sleep=lambda s: None)["rebuilt"] and run.did("build")


def test_waits_for_running_dag_runs(repo):
    run, slept = Fake(head="aaa", running=(1, 1, 0)), []
    d.deploy(repo, "bbb", run=run, sleep=slept.append)
    assert len(slept) == 2 and run.did("checkout")


def test_gives_up_if_runs_never_finish(repo):
    run = Fake(head="aaa", running=(1,))
    with pytest.raises(RuntimeError, match="DAG"):
        d.deploy(repo, "bbb", run=run, sleep=lambda s: None, wait_min=3)
    assert not run.did("checkout")                     # 코드를 바꾸지 않고 멈춤(다음에 다시)


def test_airflow_down_is_not_waiting(repo):
    def run(cmd):
        if "list-runs" in cmd:
            raise subprocess.CalledProcessError(1, cmd)   # Airflow 가 꺼져 있음
        return Fake(head="aaa")(cmd)
    assert d.deploy(repo, "aaa", run=run, sleep=lambda s: pytest.fail("기다리면 안 됨"))["to"] == "aaa"


def test_missing_folder_is_clear_error(tmp_path):
    with pytest.raises(SystemExit, match="전용 폴더"):
        d.deploy(str(tmp_path / "없음"), "bbb", run=Fake(), sleep=lambda s: None)
