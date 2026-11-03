"""
CD: 노트북 Airflow 전용 폴더를 main 의 커밋으로 바꾼다(GitHub Actions 의 노트북 러너가 부름 — .github/workflows/cd.yml).
몇 번 돌려도 같은 결과(멱등): 이미 그 커밋이면 코드는 그대로, Airflow 는 떠 있으면 그대로.

  1) 도는 DAG 실행이 있으면 끝날 때까지 기다린다(실행 도중에 코드가 바뀌지 않게, 최대 --wait-min 분).
     Airflow 가 꺼져 있으면 기다리지 않는다.
  2) git fetch → 그 커밋으로 checkout(--detach --force). 전용 폴더라 사람이 고친 파일이 없다(.env 는 git 이 건드리지 않음).
  3) Airflow 이미지·compose 설정이 바뀌었으면 build, 그다음 up -d.

전용 폴더 준비(처음 한 번, README 'CD'): git clone → job-skill/.env 복사 → 이 폴더에서 compose up -d.
사용: python deploy_airflow.py --dir C:/career-airflow --sha <커밋>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

IMAGE_FILES = ("job-skill/airflow/Dockerfile", "job-skill/airflow/requirements-airflow.txt",
               "job-skill/docker-compose.airflow.yml")
DAGS = ("daily_collect", "backfill_once")


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8").stdout


def running_runs(run, compose: list[str]) -> int:
    """지금 도는 DAG 실행 수. Airflow 가 꺼져 있으면 0."""
    n = 0
    for dag in DAGS:
        try:
            out = run([*compose, "exec", "-T", "airflow-scheduler", "airflow", "dags", "list-runs", dag,
                       "--state", "running", "-o", "json"])
        except subprocess.CalledProcessError:
            return 0
        n += len(json.loads(out.strip() or "[]"))
    return n


def deploy(repo: str, sha: str, run=sh, sleep=time.sleep, wait_min: int = 180) -> dict:
    """repo(전용 폴더, git 저장소 맨 위)를 sha 로. {"from", "to", "changed", "rebuilt"}."""
    if not os.path.isdir(os.path.join(repo, ".git")):
        sys.exit(f"Airflow 전용 폴더가 없습니다: {repo} — README 'CD' 의 준비를 먼저 하세요.")
    compose = ["docker", "compose", "-f", os.path.join(repo, "job-skill", "docker-compose.airflow.yml")]
    git = lambda *a: run(["git", "-C", repo, *a])
    for waited in range(wait_min + 1):
        if running_runs(run, compose) == 0:
            break
        if waited == wait_min:
            raise RuntimeError(f"DAG 실행이 {wait_min}분 안에 끝나지 않아 배포를 멈춤 — 코드는 그대로(다음에 다시)")
        sleep(60)
    git("fetch", "--quiet", "origin")
    old = git("rev-parse", "HEAD").strip()
    changed = old != sha
    rebuilt = False
    if changed:
        rebuilt = bool(git("diff", "--name-only", old, sha, "--", *IMAGE_FILES).strip())
        git("checkout", "--quiet", "--force", "--detach", sha)
    if rebuilt:
        run([*compose, "build"])
    run([*compose, "up", "-d"])
    return {"from": old, "to": sha, "changed": changed, "rebuilt": rebuilt}


def main() -> None:
    ap = argparse.ArgumentParser(description="노트북 Airflow 전용 폴더를 main 의 커밋으로(CD)")
    ap.add_argument("--dir", required=True, help="Airflow 전용 폴더(git 저장소 맨 위)")
    ap.add_argument("--sha", required=True, help="배포할 커밋")
    ap.add_argument("--wait-min", type=int, default=180, help="도는 DAG 실행을 기다릴 최대 분")
    args = ap.parse_args()
    out = deploy(args.dir, args.sha, wait_min=args.wait_min)
    print(f"Airflow 코드: {out['from'][:7]} -> {out['to'][:7]}" + (" (이미지 다시 만듦)" if out["rebuilt"] else "")
          + ("" if out["changed"] else " (이미 최신, 바꾼 것 없음)"))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
