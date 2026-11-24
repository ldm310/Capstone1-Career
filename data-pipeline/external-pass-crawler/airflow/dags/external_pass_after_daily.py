"""Opt-in companion DAG: wait for Daily DB save, then register/consume external reference jobs."""
import os
import subprocess
import sys
from pathlib import Path
import pendulum
from airflow.sdk import dag, task, get_current_context
from airflow.providers.standard.sensors.external_task import ExternalTaskSensor


@dag(dag_id="external_pass_after_daily",schedule="0 0 * * *",
     start_date=pendulum.datetime(2026,11,8,tz="Asia/Seoul"),catchup=False,
     max_active_runs=1,is_paused_upon_creation=True,tags=["external-pass"])
def external_pass_after_daily():
    saved=ExternalTaskSensor(task_id="wait_for_saved_postings",external_dag_id="daily_collect",
            external_task_id="load_db",allowed_states=["success"],failed_states=["failed","skipped"],
            check_existence=True,mode="reschedule",poke_interval=60,timeout=21600,retries=0)

    @task(retries=0)
    def register_and_collect():
        source=Path(os.getenv("EXTERNAL_CRAWLER_DIR","/opt/airflow/external-pass-crawler"))
        if not (source/"external_pass_crawler/comparison_batch.py").is_file():
            raise RuntimeError("External crawler package is not mounted")
        if not os.getenv("EXTERNAL_DATABASE_URL") or not os.getenv("EXTERNAL_BACKEND_URL"):
            raise RuntimeError("External collection runtime configuration is missing")
        start=get_current_context()["data_interval_start"].isoformat()
        env={**os.environ,"DATABASE_URL":os.environ["EXTERNAL_DATABASE_URL"],
             "BACKEND_URL":os.environ["EXTERNAL_BACKEND_URL"],"PYTHONDONTWRITEBYTECODE":"1",
             "PYTHONPATH":str(source)+os.pathsep+os.environ.get("PYTHONPATH","")}
        result=subprocess.run([sys.executable,"-m","external_pass_crawler.comparison_batch","--since",start],
                              cwd=source,env=env,capture_output=True)
        if result.returncode:
            raise RuntimeError("External collection batch failed; inspect safe CLI error codes")
        # The CLI prints safe counters/codes only. Source text and connection values are never logged.
        print(result.stdout.decode("utf-8",errors="replace"))

    saved >> register_and_collect()


external_pass_after_daily()
