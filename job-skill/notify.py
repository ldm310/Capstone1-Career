"""
Slack 알림 (#data-pipeline). 웹훅 주소는 환경변수 SLACK_WEBHOOK_URL, 없으면 이 폴더의 .env 에서 읽는다.
메시지에는 숫자·상태·오류 종류만 넣는다 — 공고 제목·회사·본문은 넣지 않는다.
실패해서 넘어간 공고는 공고번호·원인·사람인 공개 링크까지 넣는다(사용자 결정 — 어느 공고인지 바로 찾아보게).
보내기에 실패해도 예외를 던지지 않는다(알림 때문에 파이프라인이 멈추지 않게).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
POSTING_URL = "https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=list&rec_idx={no}"
SHOW = 10  # 알림 한 번에 보여 줄 공고 수(나머지는 '외 N건')
log = logging.getLogger(__name__)


class PostingsFailed(RuntimeError):
    """공고 몇 개가 실패해 태스크를 실패시킬 때. 실패 알림(on_failure)에 공고번호·원인·링크를 붙인다."""

    def __init__(self, what: str, items: list[tuple[str, str]]):
        self.what, self.items = what, list(items)
        super().__init__(f"{what} {len(self.items)}건")


def posting_lines(items: list[tuple[str, str]]) -> str:
    """'• 공고번호 원인 링크' 한 줄씩, SHOW 건까지."""
    lines = [f"• {no} {why} {POSTING_URL.format(no=no)}" for no, why in items[:SHOW]]
    if len(items) > SHOW:
        lines.append(f"…외 {len(items) - SHOW}건(태스크 로그)")
    return "\n".join(lines)


def webhook_url() -> str | None:
    if os.environ.get("SLACK_WEBHOOK_URL"):
        return os.environ["SLACK_WEBHOOK_URL"]
    if os.path.exists(ENV_PATH):
        for ln in open(ENV_PATH, encoding="utf-8"):
            k, _, v = ln.strip().partition("=")
            if k == "SLACK_WEBHOOK_URL" and v:
                return v
    return None


def send(text: str) -> bool:
    """Slack 채널로 보낸다. 성공하면 True, 웹훅이 없거나 실패하면 False(예외 없음)."""
    url = webhook_url()
    if not url:
        log.warning("SLACK_WEBHOOK_URL 이 없어 Slack 알림을 보내지 않음: %s", text)
        return False
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:  # 알림 실패로 태스크를 실패시키지 않는다
        log.warning("Slack 알림 실패: %s", e)
        return False


def _value(name: str, v) -> str:
    return f"${v:.2f}" if "비용" in name else f"{v}"


def msg_result(dag_label: str, counts: dict) -> str:
    """'✅ 매일 수집 완료 · 새 공고 52 · 추출 52 · 확인 필요 2 · 오늘 비용 $0.21' (키 순서대로)."""
    return " · ".join([f"✅ {dag_label} 완료"] + [f"{k} {_value(k, v)}" for k, v in counts.items()])


def msg_failure(dag_id: str, task_id: str, try_number: int, exc: BaseException | None) -> str:
    head = f"❌ {dag_id} · {task_id} 실패 ({try_number}번째 시도)"
    if isinstance(exc, PostingsFailed):
        return f"{head} · {exc}\n{posting_lines(exc.items)}"
    return head if exc is None else f"{head} · {type(exc).__name__}: {str(exc)[:200]}"


def msg_budget(dag_label: str, spent: float, limit: float, left: int) -> str:
    return (f"⚠️ {dag_label}: 비용 상한 ${limit:.2f} 도달로 LLM 추출 멈춤 · 쓴 비용 ${spent:.2f} · "
            f"남은 공고 {left}건은 다음 실행 때")


def msg_skipped(dag_label: str, what: str, items: list[tuple[str, str]], after: str) -> str:
    """태스크는 계속하고 넘어간 공고들: '⚠️ 매일 수집: LLM 추출 실패 2건 — 결과 없이 저장하고 넘어감' + 공고 줄."""
    return f"⚠️ {dag_label}: {what} {len(items)}건 — {after}\n{posting_lines(items)}"


def msg_daily_cost(day: dt.date, usd: float, runs: int) -> str:
    return f"💰 {day.month}월 {day.day}일 LLM 비용 ${usd:.2f} (추출 {runs}건)"


def on_failure(context: dict) -> None:
    """Airflow on_failure_callback: 재시도까지 다 실패한 태스크를 알린다."""
    ti = context["ti"]
    send(msg_failure(ti.dag_id, ti.task_id, ti.try_number, context.get("exception")))
