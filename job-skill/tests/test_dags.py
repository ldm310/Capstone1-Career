"""DAG 3개 구조 시험 — Airflow 컨테이너 안에서만 돈다(노트북 파이썬에는 Airflow 가 없어 건너뜀).
실행: docker compose -f docker-compose.airflow.yml exec airflow-scheduler python -m pytest /opt/airflow/job-skill/tests/test_dags.py -v
"""
from __future__ import annotations

import datetime as dt
import os

import pytest

pytest.importorskip("airflow.sdk")   # job-skill/airflow/ 폴더가 이름공간 패키지로 잡히지 않게 sdk 로 확인

DAG_FOLDER = os.environ.get("AIRFLOW_DAGS", "/opt/airflow/dags")


@pytest.fixture(scope="module")
def bag():
    try:
        from airflow.dag_processing.dagbag import DagBag
    except ImportError:
        from airflow.models.dagbag import DagBag
    return DagBag(dag_folder=DAG_FOLDER)   # 3.3 에는 include_examples 인자가 없다(예시 DAG 는 LOAD_EXAMPLES=false 로 끔)


def test_no_import_errors(bag):
    assert bag.import_errors == {}


def test_dag_ids_and_schedules(bag):
    assert {"backfill_once", "daily_collect", "recheck_postings"} <= set(bag.dag_ids)
    assert bag.get_dag("backfill_once").schedule is None
    assert bag.get_dag("daily_collect").schedule == "0 0 * * *"
    # 3일 간격(timedelta)은 늦게 켜거나 노트북이 꺼졌다 켜지면 12:00 에서 밀려 ①(00:00)과 겹칠 수 있다 → 날짜 cron
    assert bag.get_dag("recheck_postings").schedule == "0 12 */3 * *"
    for dag_id in ("backfill_once", "daily_collect", "recheck_postings"):
        d = bag.get_dag(dag_id)
        assert d.timezone.name == "Asia/Seoul" and d.max_active_runs == 1 and d.catchup is False
    # ①② 는 꺼진 채로 올라오고, ③ 은 일정이 없어 켜진 채(바로 수동 실행)
    assert bag.get_dag("backfill_once").is_paused_upon_creation is False
    assert bag.get_dag("daily_collect").is_paused_upon_creation is True
    assert bag.get_dag("recheck_postings").is_paused_upon_creation is True


def test_daily_task_graph(bag):
    d = bag.get_dag("daily_collect")
    cost = d.get_task("notify_cost")
    assert cost.upstream_task_ids == set() and cost.downstream_task_ids == set()
    assert d.get_task("collect_list").downstream_task_ids == {"fetch_raw"}
    assert d.get_task("extract_llm").upstream_task_ids == {"fetch_raw", "image_processing.filter_sections"}
    assert d.get_task("notify_result").upstream_task_ids == {"load_db"}
    assert "close_postings" not in d.task_ids


def test_backfill_task_graph(bag):
    d = bag.get_dag("backfill_once")
    assert d.get_task("collect_list").upstream_task_ids == set()
    assert d.get_task("image_processing.ocr_images").upstream_task_ids == {"fetch_raw"}
    assert d.get_task("image_processing.ocr_images").downstream_task_ids == {"image_processing.filter_sections"}
    assert d.get_task("notify_result").upstream_task_ids == {"load_db"}
    assert "notify_cost" not in d.task_ids


def test_recheck_task_graph(bag):
    d = bag.get_dag("recheck_postings")
    assert d.get_task("scan_lists").downstream_task_ids == {"detect_changes"}
    assert d.get_task("detect_changes").downstream_task_ids == {"close_postings", "fetch_raw"}
    assert d.get_task("notify_result").upstream_task_ids == {"load_db", "close_postings"}


def test_all_tasks_retry_and_alert(bag):
    import notify
    for dag_id in ("backfill_once", "daily_collect", "recheck_postings"):
        for t in bag.get_dag(dag_id).tasks:
            cb = t.on_failure_callback
            cbs = cb if isinstance(cb, list) else [cb]
            assert t.retries == 2, (dag_id, t.task_id)
            assert notify.on_failure in cbs, (dag_id, t.task_id)
