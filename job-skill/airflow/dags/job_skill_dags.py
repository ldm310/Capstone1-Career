"""
채용공고 역량 추출 DAG 2개 (사람인 백엔드·데이터 엔지니어, 경력 필터 신입·3년 이하·경력무관).

  ③ backfill_once  수동 1회   — 진행 중인 대상 공고 전부를 수집해 DB 저장까지
  ① daily_collect  매일 00:00 — 목록 전체를 보고 새 공고(+ 밀린 공고) 수집, '수정'된 공고는 본문 지문 비교로 바뀐 것만 다시 추출,
                                목록에서 사라진 공고는 전체 페이지의 '접수마감'으로 마감, 마감일 반영
(예전 ② 수정 확인은 ① 에 합침 — 사람인이 '수정' 표시를 약 24시간만 보여 줘서 매일 봐야 함, 사용자 결정)

① 은 꺼진 채로 올라온다(③ 은 일정이 없어 켜진 채). ③ 이 끝나면 관리 화면에서 ① 을 켠다.
① 을 켜는 순간 놓친 가장 최근 회차가 한 번 바로 돈다(Airflow catchup=False 기본 동작). 그다음부터 매일 00:00.
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
# 자리 1개짜리 풀(airflow-init 이 만듦): ③ 과 ① 이 겹쳐 돌아도(③ 이 끝나기 전에 ① 을 켬 등)
# 사람인 요청은 한 번에 한 태스크(초당 1건), GPU OCR 도 하나, LLM 추출도 하나씩
SARAMIN, GPU, LLM = "saramin", "gpu", "llm"
MAX_NEW = {"max_new": Param(None, type=["null", "integer"], minimum=1,
                            description="시험용: 새 공고를 이 수까지만 (비우면 전부)")}


def _ctx():
    return get_current_context()


def _run_dir() -> str:
    c = _ctx()
    return pt.run_dir_for(c["dag"].dag_id, c["run_id"])


def _process(label: str, limit: float, daily: bool):
    """공고 원본 수집 → [이미지 처리: 이미지 OCR → 불필요 단락 제거] → LLM 추출 → DB 저장. 글 공고는 원본 수집에서 바로 추출로."""

    @task(task_display_name="공고 원본 수집", pool=SARAMIN)
    def fetch_raw():
        return pt.step_fetch_raw(_run_dir())

    @task_group(group_id="image_processing", group_display_name="이미지 처리")
    def image_processing():
        @task(task_display_name="이미지 OCR", pool=GPU)
        def ocr_images():
            pt.step_ocr(_run_dir())

        @task(task_display_name="불필요 단락 제거")
        def filter_sections():
            pt.step_filter(_run_dir())

        ocr_images() >> filter_sections()   # 값을 돌려주면 화살표가 마지막 태스크에만 붙는다

    @task(task_display_name="LLM 추출", pool=LLM)
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
    """오늘 ① LLM 비용(하루 상한과 같은 셈)."""
    return pt.day_spent(db_queries.today_kst())[0]


def _send_result(label: str, counts: dict) -> None:
    notify.send(notify.msg_result(label, counts))


@dag(dag_id="backfill_once", dag_display_name="③ 일회성 전체 수집", schedule=None, start_date=START, params=MAX_NEW,
     is_paused_upon_creation=False,  # 일정이 없어 켜 둬도 저절로 돌지 않는다 — 바로 수동 실행할 수 있게
     doc_md=__doc__, **COMMON)
def backfill_once():
    @task(task_display_name="공고 목록 수집", pool=SARAMIN)
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
        """어제(KST) LLM 비용 합계(DB 기준)."""
        yesterday = db_queries.today_kst() - dt.timedelta(days=1)
        with connect() as conn:
            usd, runs = db_queries.day_cost(conn, yesterday)
        notify.send(notify.msg_daily_cost(yesterday, usd, runs))

    @task(task_display_name="공고 목록 수집", pool=SARAMIN)
    def collect_list():
        return pt.step_collect(_run_dir(), include_pending=True, max_new=_ctx()["params"].get("max_new"))

    @task(task_display_name="변경 감지", pool=SARAMIN)
    def detect_changes():
        return pt.step_detect(_run_dir())

    @task(task_display_name="마감 처리")
    def close_postings():
        return pt.step_close(_run_dir())

    @task(task_display_name="결과 알림")
    def notify_result():
        ti = _ctx()["ti"]
        got = ti.xcom_pull(task_ids="collect_list") or {}
        seen = ti.xcom_pull(task_ids="detect_changes") or {}
        s = pt.summary(_run_dir())
        _send_result("매일 수집", {"새 공고": got.get("new", 0), "밀린 공고": got.get("pending", 0),
                               "수정": got.get("수정", 0), "바뀜": seen.get("바뀜", 0),
                               "목록에 없음": got.get("목록에 없음", 0), "마감": ti.xcom_pull(task_ids="close_postings") or 0,
                               "마감일 바뀜": got.get("마감일 바뀜", 0), "오류": seen.get("오류", 0),
                               "추출": s["추출"], "확인 필요": s["확인 필요"], "비용": s["비용"],
                               "오늘 비용": _today_cost()})

    notify_cost()
    detect = detect_changes()
    collect_list() >> detect
    close = close_postings()
    raw, load = _process("매일 수집", pt.DAILY_LIMIT, daily=True)
    detect >> [close, raw]
    [load, close] >> notify_result()


backfill_once()
daily_collect()
