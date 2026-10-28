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
import recheck
from db_load import connect

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL, TAG = "gpt-5.6-luna", "-ex"
RUN_NAME = MODEL + TAG
DAILY_LIMIT = 5.0      # 하루(KST) ①+② 합산
BACKFILL_LIMIT = 10.0  # ③ 한 번 실행
DAILY_DAGS = ("daily_collect", "recheck_postings")  # 하루 상한을 같이 쓰는 DAG


def _abs(run_dir: str) -> str:
    return os.path.join(HERE, run_dir)


def run_dir_for(dag_id: str, run_id: str) -> str:
    return f"data/runs/{dag_id}/" + re.sub(r"[^0-9A-Za-z_.-]", "_", run_id)


def run_script(script: str, args: list[str], run_dir: str, python: str | None = None) -> None:
    env = {**os.environ, "OCR_DATA_DIR": run_dir, "PYTHONIOENCODING": "utf-8"}
    subprocess.run([python or sys.executable, script, *args], cwd=HERE, env=env, check=True)


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
    """공고 목록 수집.
    ①(include_pending): 밀린 공고(추출 결과가 없는 진행 공고)를 맨 위에 두고, 아는 번호가 연속 5개면 멈춘다.
    ③: 연속 멈춤 없이 목록 끝까지 보며 아는 번호만 건너뛴다 — 시험·실패로 일부만 저장된 뒤 다시 돌려도 이어서 하게.
    버린 공고는 <run_dir>/excluded.json 에만 두고, DB 기록은 DB 저장에 성공한 뒤(step_load) 한다."""
    d = _abs(run_dir)
    with connect() as conn:
        known = db_queries.known_posting_nos(conn)
        res = collect.collect_list(d, known, max_new=max_new, stop_after=5 if include_pending else None)
        pending = db_queries.pending_postings(conn) if include_pending else []
    with open(os.path.join(d, "excluded.json"), "w", encoding="utf-8") as f:
        json.dump(res["excluded"], f, ensure_ascii=False)
    first = {r["rec_idx"] for r in pending}
    new = [r for r in res["targets"] if r["rec_idx"] not in first]
    collect.write_targets(d, pending + new)
    return {"new": len(new), "pending": len(pending), "excluded": len(res["excluded"])}


def step_pick_recheck(run_dir: str) -> dict:
    """공고 목록 확인(②): 두 직무 목록 전체를 보고, 마지막 확인 뒤 '수정'된 진행 공고 + 목록에서 사라진 진행 공고를 고른다.
    고른 공고는 <run_dir>/check.json 으로 변경 감지에 넘긴다. DB 는 목록을 보는 동안 열어 두지 않는다.
    목록에 보이는 공고의 마감일은 본문 확인과 상관없이 DB 에 반영한다(마감일은 본문 밖이라 지문으로는 안 잡힘)."""
    today = db_queries.today_kst()
    with connect() as conn:
        rows = db_queries.open_postings(conn)
    listed = collect.scan_lists()
    check, counts = recheck.select_recheck(listed, rows, today)
    deadlines = {no: d for no, it in listed.items() if (d := collect.parse_deadline(it.get("deadline_text", ""), today))}
    with connect() as conn:
        counts["마감일 바뀜"] = db_queries.update_deadlines(conn, deadlines)
    d = _abs(run_dir)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "check.json"), "w", encoding="utf-8") as f:
        json.dump(check, f, ensure_ascii=False, default=str)
    return counts


def step_detect(run_dir: str) -> dict:
    """변경 감지(②): 고른 공고의 본문만 다시 받아 지문 비교 → 바뀐 공고는 targets.tsv(다시 추출), 결과는 changes.json.
    그대로인 공고만 확인 시각을 지금으로 바꾼다. 바뀐 공고는 다시 추출해 DB 저장에 성공할 때 바뀐다(실패하면 다음 ②가 다시)."""
    d = _abs(run_dir)
    rows = json.load(open(os.path.join(d, "check.json"), encoding="utf-8"))
    res = recheck.detect_changes(d, rows)
    with connect() as conn:
        db_queries.touch_checked(conn, res["unchanged"])
    return {"확인": len(rows), "바뀜": len(res["changed"]), "그대로": len(res["unchanged"]), "오류": len(res["error"])}


def step_close(run_dir: str) -> int:
    """마감 처리(②): 본문이 없어진 공고를 '마감'으로."""
    res = json.load(open(os.path.join(_abs(run_dir), "changes.json"), encoding="utf-8"))
    with connect() as conn:
        return db_queries.mark_closed(conn, res["closed"])


def step_fetch_raw(run_dir: str) -> dict:
    """공고 원본 수집(본문·이미지) → 글/이미지 종류 채우기. targets 가 비면 아무것도 안 함."""
    if not _targets(run_dir):
        return {}
    run_script("fetch_images.py", [], run_dir)
    return collect.classify_targets(_abs(run_dir))


def step_ocr(run_dir: str) -> None:
    """이미지 OCR — 항상 GPU(--gpu). GPU 가 없으면 스크립트가 실패하고 Airflow 가 재시도·Slack 으로 알린다.
    PaddleOCR 은 Airflow 와 패키지 버전(PyYAML)이 부딪쳐 이미지 안 별도 가상환경(OCR_PYTHON)에서 돈다."""
    if _has_images(run_dir):
        run_script("dump_paddle_boxes.py", ["--gpu"], run_dir, python=os.environ.get("OCR_PYTHON") or sys.executable)


def step_filter(run_dir: str) -> None:
    """불필요 단락 제거(rule base) + 표 정리 입력 만들기."""
    if _has_images(run_dir):
        run_script("section_split.py", ["--paddle-only"], run_dir)


def day_spent(day: dt.date, base: str | None = None) -> tuple[float, int]:
    """그날(KST) ①+② 가 LLM 에 쓴 돈과 추출 수 — 하루 상한용. ③ 은 따로($10)라 세지 않는다.
    DB 가 아니라 실행 폴더의 결과 파일(run_at)로 센다: 아직 DB 에 안 들어간 결과(추출 재시도, 실패한 실행,
    같이 도는 다른 실행)도 빠짐없이 들어가게."""
    base = base or os.path.join(HERE, "data", "runs")
    usd, n = 0.0, 0
    for dag_id in DAILY_DAGS:
        for path in glob.glob(os.path.join(base, dag_id, "*", "out", "extract", RUN_NAME, "*.json")):
            r = json.load(open(path, encoding="utf-8"))
            at = r.get("run_at")
            if at and dt.datetime.fromisoformat(at).astimezone(db_queries.KST).date() == day:
                usd += r.get("cost_usd") or 0
                n += 1
    return round(usd, 6), n


def extract_budget(run_dir: str, limit: float, daily: bool) -> float:
    """이번 LLM 추출에 쓸 수 있는 돈.
    ③: 실행 한 번에 limit 에서 이 실행 폴더가 이미 쓴 돈(추출 재시도 때 지난 시도 몫)을 뺀다.
    ①②: 하루 limit 에서 오늘 ①+② 가 쓴 돈(day_spent — 이 실행 폴더도 들어 있음)을 뺀다."""
    spent = day_spent(db_queries.today_kst())[0] if daily else summary(run_dir)["비용"]
    return max(0.0, round(limit - spent, 6))


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
    """DB 저장. 추출 결과가 없는 공고도 공고로는 넣는다(다음 ① 때 밀린 공고로 다시 추출).
    공고를 저장한 뒤에 버린 공고(excluded.json)를 기록한다 — 앞 단계가 실패한 실행의 버린 공고는 '아는 번호'가 되지 않게."""
    total = {}
    if _targets(run_dir):
        result = os.path.join(_abs(run_dir), "out", "load_result.json")
        if os.path.exists(result):  # 지난 시도의 결과 — 이번 결과와 헷갈리지 않게
            os.remove(result)
        try:
            run_script("db_load.py", ["load", "--run", RUN_NAME], run_dir)
        except subprocess.CalledProcessError as e:
            failed = json.load(open(result, encoding="utf-8"))["failed"] if os.path.exists(result) else []
            if failed:  # Airflow 가 태스크를 다시 하고, 그래도 안 되면 이 문장이 Slack 실패 알림에 실린다(숫자만)
                raise RuntimeError(f"DB 저장 실패 {len(failed)}건 — 공고마다 여러 번 다시 해도 실패(공고번호는 태스크 로그)") from e
            raise
        if os.path.exists(result):
            total = json.load(open(result, encoding="utf-8"))["total"]
    path = os.path.join(_abs(run_dir), "excluded.json")
    if os.path.exists(path):
        rows = [tuple(r) for r in json.load(open(path, encoding="utf-8"))]
        with connect() as conn:
            db_queries.record_excluded(conn, rows)
    return total


def summary(run_dir: str) -> dict:
    """결과 알림용 숫자: 처리한 공고 수, 추출 결과 수, 확인 필요 수, 이번 실행 LLM 비용."""
    results = []
    for path in glob.glob(os.path.join(_abs(run_dir), "out", "extract", RUN_NAME, "*.json")):
        results.append(json.load(open(path, encoding="utf-8")))
    review = sum(1 for r in results if r.get("review_reasons") or r.get("check_flag"))
    cost = round(sum(r.get("cost_usd", 0) or 0 for r in results), 6)
    return {"새 공고": len(_targets(run_dir)), "추출": len(results), "확인 필요": review, "비용": cost}
