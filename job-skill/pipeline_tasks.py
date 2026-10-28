"""
Airflow 태스크가 부르는 함수들. DAG 파일은 순서만 정하고, 상자 하나하나의 일은 여기서 한다.

실행(DAG run)마다 실행 폴더 data/runs/<dag_id>/<run_id>/ 를 만들고, 그 안의 targets.tsv 가 단계 사이의 작업 목록이다.
기존 스크립트(fetch_images·dump_paddle_boxes·section_split·extract_skills·db_load)는 common.py 가 import 할 때
경로를 정하므로 OCR_DATA_DIR=<실행 폴더> 로 새 프로세스에서 돌린다(run_script).
run_dir 은 이 폴더(job-skill) 기준 상대 경로(절대 경로도 됨).
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

import collect
import db_queries
import notify
from db_load import connect

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL, TAG = "gpt-5.6-luna", "-ex"
RUN_NAME = MODEL + TAG
DAILY_LIMIT = 5.0      # 하루(KST) ①+② 합산
BACKFILL_LIMIT = 10.0  # ③ 한 번 실행


def _abs(run_dir: str) -> str:
    return os.path.join(HERE, run_dir)


def run_dir_for(dag_id: str, run_id: str) -> str:
    return f"data/runs/{dag_id}/" + re.sub(r"[^0-9A-Za-z_.-]", "_", run_id)


def run_script(script: str, args: list[str], run_dir: str) -> None:
    env = {**os.environ, "OCR_DATA_DIR": run_dir, "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, script, *args], cwd=HERE, env=env, check=True)


def _targets(run_dir: str) -> list[dict]:
    return collect.read_targets(_abs(run_dir))


def _has_images(run_dir: str) -> bool:
    path = os.path.join(_abs(run_dir), "images", "manifest.tsv")
    if not os.path.exists(path):
        return False
    import csv
    with open(path, encoding="utf-8") as f:
        return any(r.get("file") for r in csv.DictReader(f, delimiter="\t"))


def step_collect(run_dir: str, include_pending: bool, max_new: int | None = None) -> dict:
    """공고 목록 수집. include_pending 이면 밀린 공고(추출 결과가 없는 진행 공고)를 맨 위에 둔다."""
    d = _abs(run_dir)
    with connect() as conn:
        known = db_queries.known_posting_nos(conn)
        res = collect.collect_list(d, known, max_new=max_new)
        db_queries.record_excluded(conn, res["excluded"])
        pending = db_queries.pending_postings(conn) if include_pending else []
    first = {r["rec_idx"] for r in pending}
    new = [r for r in res["targets"] if r["rec_idx"] not in first]
    collect.write_targets(d, pending + new)
    return {"new": len(new), "pending": len(pending), "excluded": len(res["excluded"])}


def step_fetch_raw(run_dir: str) -> dict:
    """공고 원본 수집(본문·이미지) → 글/이미지 종류 채우기. targets 가 비면 아무것도 안 함."""
    if not _targets(run_dir):
        return {}
    run_script("fetch_images.py", [], run_dir)
    return collect.classify_targets(_abs(run_dir))


def step_ocr(run_dir: str) -> None:
    """이미지 OCR — 항상 GPU(--gpu). GPU 가 없으면 스크립트가 실패하고 Airflow 가 재시도·Slack 으로 알린다."""
    if _has_images(run_dir):
        run_script("dump_paddle_boxes.py", ["--gpu"], run_dir)


def step_filter(run_dir: str) -> None:
    """불필요 단락 제거(rule base) + 표 정리 입력 만들기."""
    if _has_images(run_dir):
        run_script("section_split.py", ["--paddle-only"], run_dir)


def budget_left(conn, limit: float, day: dt.date) -> float:
    return max(0.0, limit - db_queries.day_cost(conn, day)[0])


def step_extract(run_dir: str, budget_usd: float, dag_label: str, limit: float | None = None) -> dict:
    """LLM 추출 + 표준화 + 모집 단위 검사. budget_usd 만큼만 쓰고, 상한에 닿으면 Slack 으로 한 번 알린다.
    limit 은 알림에 적을 상한(하루 $5 또는 ③ $10), 없으면 budget_usd."""
    targets = _targets(run_dir)
    if not targets:
        return {"stopped": False}
    limit = budget_usd if limit is None else limit
    if budget_usd <= 0:
        notify.send(notify.msg_budget(dag_label, limit - budget_usd, limit, len(targets)))
        return {"stopped": True, "left": len(targets)}
    budget_path = os.path.join(_abs(run_dir), "out", "extract", "_budget.json")
    if os.path.exists(budget_path):  # 지난 시도의 기록 — 이번 실행에서 다시 알리지 않게 지운다
        os.remove(budget_path)
    run_script("extract_skills.py", ["--models", MODEL, "--effort", "low", "--examples", f"--tag={TAG}",
                                     "--max-usd", f"{budget_usd}"], run_dir)
    if not os.path.exists(budget_path):
        return {"stopped": False}
    b = json.load(open(budget_path, encoding="utf-8"))
    notify.send(notify.msg_budget(dag_label, (limit - budget_usd) + b["spent"], limit, b["left"]))
    return {"stopped": True, "left": b["left"]}


def step_load(run_dir: str) -> dict:
    """DB 저장. 추출 결과가 없는 공고도 공고로는 넣는다(다음 ① 때 밀린 공고로 다시 추출)."""
    if not _targets(run_dir):
        return {}
    run_script("db_load.py", ["load", "--run", RUN_NAME], run_dir)
    return {}


def summary(run_dir: str) -> dict:
    """결과 알림용 숫자: 처리한 공고 수, 추출 결과 수, 확인 필요 수, 이번 실행 LLM 비용."""
    results = []
    for path in glob.glob(os.path.join(_abs(run_dir), "out", "extract", RUN_NAME, "*.json")):
        results.append(json.load(open(path, encoding="utf-8")))
    review = sum(1 for r in results if r.get("review_reasons") or r.get("check_flag"))
    cost = round(sum(r.get("cost_usd", 0) or 0 for r in results), 6)
    return {"새 공고": len(_targets(run_dir)), "추출": len(results), "확인 필요": review, "비용": cost}
