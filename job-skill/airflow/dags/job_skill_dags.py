"""
채용공고 역량 추출 DAG 3개 (사람인 백엔드·데이터 엔지니어, 경력 0~3년).

  ③ backfill_once     수동 1회   — 진행 중인 대상 공고 전부를 수집해 DB 저장까지
  ① daily_collect     매일 00:00 — 새 공고(+ 추출 못 한 밀린 공고)만
  ② recheck_postings  3일마다 12:00(매달 1·4·7…31일) — 목록에서 '수정'·사라진 공고만 본문 확인 → 바뀐 공고 다시 추출, 없어진 공고 마감

①·②는 꺼진 채로 올라온다(③은 일정이 없어 켜진 채). ③이 끝나면 관리 화면에서 ①·②를 켠다.
상자 하나하나의 일은 job-skill/pipeline_tasks.py 에 있고, 여기서는 순서만 정한다.
태스크 사이에는 실행 폴더(data/runs/<dag_id>/<run_id>/)의 파일로 넘기고, XCom 에는 작은 숫자만 넣는다.
"""

from __future__ import annotations

import datetime as dt

import pendulum
from airflow.sdk import Param, dag, get_current_context, task, task_group

import db_queries
import notify
import pipeline_tasks as pt
from db_load import connect

DEFAULT_ARGS = {"retries": 2, "retry_delay": dt.timedelta(minutes=5), "on_failure_callback": notify.on_failure}
COMMON = dict(default_args=DEFAULT_ARGS, max_active_runs=1, catchup=False, tags=["job-skill"])
START = pendulum.datetime(2026, 10, 28, tz="Asia/Seoul")
MAX_NEW = {"max_new": Param(None, type=["null", "integer"], minimum=1,
                            description="시험용: 새 공고를 이 수까지만 (비우면 전부)")}


def _ctx():
    return get_current_context()


def _run_dir() -> str:
    c = _ctx()
    return pt.run_dir_for(c["dag"].dag_id, c["run_id"])


def _process(label: str, limit: float, daily: bool):
    """공고 원본 수집 → [이미지 처리: 이미지 OCR → 불필요 단락 제거] → LLM 추출 → DB 저장. 글 공고는 원본 수집에서 바로 추출로."""

    @task(task_display_name="공고 원본 수집")
    def fetch_raw():
        return pt.step_fetch_raw(_run_dir())

    @task_group(group_id="image_processing", group_display_name="이미지 처리")
    def image_processing():
        @task(task_display_name="이미지 OCR")
        def ocr_images():
            pt.step_ocr(_run_dir())

        @task(task_display_name="불필요 단락 제거")
        def filter_sections():
            pt.step_filter(_run_dir())

        ocr_images() >> filter_sections()   # 값을 돌려주면 화살표가 마지막 태스크에만 붙는다

    @task(task_display_name="LLM 추출")
    def extract_llm():
        d = _run_dir()
        return pt.step_extract(d, pt.extract_budget(d, limit, daily), label, limit=limit)

    @task(task_display_name="DB 저장")
    def load_db():
        return pt.step_load(_run_dir())

    raw = fetch_raw()
    extract = extract_llm()
    raw >> image_processing() >> extract
    raw >> extract
    load = load_db()
    extract >> load
    return raw, load


def _today_cost() -> float:
    with connect() as conn:
        return db_queries.day_cost(conn, db_queries.today_kst())[0]


def _send_result(label: str, counts: dict) -> None:
    notify.send(notify.msg_result(label, counts))


@dag(dag_id="backfill_once", dag_display_name="③ 일회성 전체 수집", schedule=None, start_date=START, params=MAX_NEW,
     is_paused_upon_creation=False,  # 일정이 없어 켜 둬도 저절로 돌지 않는다 — 바로 수동 실행할 수 있게
     doc_md=__doc__, **COMMON)
def backfill_once():
    @task(task_display_name="공고 목록 수집")
    def collect_list():
        return pt.step_collect(_run_dir(), include_pending=False, max_new=_ctx()["params"].get("max_new"))

    @task(task_display_name="결과 알림")
    def notify_result():
        _send_result("전체 수집", pt.summary(_run_dir()))

    raw, load = _process("전체 수집", pt.BACKFILL_LIMIT, daily=False)
    collect_list() >> raw
    load >> notify_result()


@dag(dag_id="daily_collect", dag_display_name="① 매일 수집", schedule="0 0 * * *", start_date=START,
     is_paused_upon_creation=True, params=MAX_NEW, doc_md=__doc__, **COMMON)
def daily_collect():
    @task(task_display_name="비용 알림")
    def notify_cost():
        """어제(KST) ①+② LLM 비용 합계."""
        yesterday = db_queries.today_kst() - dt.timedelta(days=1)
        with connect() as conn:
            usd, runs = db_queries.day_cost(conn, yesterday)
        notify.send(notify.msg_daily_cost(yesterday, usd, runs))

    @task(task_display_name="공고 목록 수집")
    def collect_list():
        return pt.step_collect(_run_dir(), include_pending=True, max_new=_ctx()["params"].get("max_new"))

    @task(task_display_name="결과 알림")
    def notify_result():
        got = _ctx()["ti"].xcom_pull(task_ids="collect_list") or {}
        s = pt.summary(_run_dir())
        _send_result("매일 수집", {"새 공고": got.get("new", 0), "밀린 공고": got.get("pending", 0),
                               "추출": s["추출"], "확인 필요": s["확인 필요"], "비용": s["비용"],
                               "오늘 비용": _today_cost()})

    notify_cost()
    raw, load = _process("매일 수집", pt.DAILY_LIMIT, daily=True)
    collect_list() >> raw
    load >> notify_result()


# 매달 1·4·7…28·31일 12:00 (달이 바뀔 때만 간격이 1~2일). 3일 간격(timedelta)은 늦게 켜거나 노트북이 꺼졌다 켜지면
# 그 시각부터 다시 세어 12:00 에서 밀리고 ①(00:00)과 겹칠 수 있어서 날짜 cron 으로 둔다.
# (①·② 모두 켜는 순간 놓친 가장 최근 회차가 한 번 바로 돈다 — Airflow catchup=False 기본 동작. 그다음부터 정해진 시각)
@dag(dag_id="recheck_postings", dag_display_name="② 수정 확인", schedule="0 12 */3 * *", start_date=START,
     is_paused_upon_creation=True, doc_md=__doc__, **COMMON)
def recheck_postings():
    @task(task_display_name="공고 목록 확인")
    def scan_lists():
        return pt.step_pick_recheck(_run_dir())

    @task(task_display_name="변경 감지")
    def detect_changes():
        return pt.step_detect(_run_dir())

    @task(task_display_name="마감 처리")
    def close_postings():
        return pt.step_close(_run_dir())

    @task(task_display_name="결과 알림")
    def notify_result():
        ti = _ctx()["ti"]
        picked = ti.xcom_pull(task_ids="scan_lists") or {}
        seen = ti.xcom_pull(task_ids="detect_changes") or {}
        s = pt.summary(_run_dir())
        _send_result("수정 확인", {"진행": picked.get("진행", 0), "수정": picked.get("수정", 0),
                               "목록에 없음": picked.get("목록에 없음", 0), "바뀜": seen.get("바뀜", 0),
                               "마감": ti.xcom_pull(task_ids="close_postings") or 0, "오류": seen.get("오류", 0),
                               "추출": s["추출"], "비용": s["비용"], "오늘 비용": _today_cost()})

    detect = detect_changes()
    scan_lists() >> detect
    close = close_postings()
    raw, load = _process("수정 확인", pt.DAILY_LIMIT, daily=True)
    detect >> [close, raw]
    done = notify_result()
    [load, close] >> done


backfill_once()
daily_collect()
recheck_postings()
