"""
Slack 알림 (#data-pipeline). 웹훅 주소는 환경변수 SLACK_WEBHOOK_URL, 없으면 이 폴더의 .env 에서 읽는다.
메시지에는 숫자·상태·오류 종류만 넣는다 — 공고 제목·회사·본문은 넣지 않는다.
실패해서 넘어간 공고는 공고번호·원인·사람인 공개 링크까지 넣는다(사용자 결정 — 어느 공고인지 바로 찾아보게).
보내기에 실패해도 예외를 던지지 않는다(알림 때문에 파이프라인이 멈추지 않게).
"""

from __future__ import annotations

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


def msg_report(dag_label: str, rows: list[tuple[str, str]], skipped: dict[str, list] | None = None,
               budget: dict | None = None, dictionary: list[str] | None = None) -> str:
    """DAG 가 끝날 때 보내는 결과 알림 하나(2026-10-31 사용자 요청 — 중간 알림 없이 결과로만, 줄을 나눠 읽기 쉽게).
      ✅ 매일 수집 완료
      • 수집: 새 공고 143 · 밀린 공고 8
      ⚠️ 비용 상한 …(멈췄을 때만)
      ⚠️ 넘어간 공고 2건 — 다음 실행 때 다시 시도
      • <링크|50846359> LLM 추출 실패 · 응답 잘림·형식 오류      (공고번호에 사람인 링크, SHOW 건까지)
    skipped: {종류: [(공고번호, 원인), …]}, budget: {"limit": 상한, "left": 남은 공고 수},
    dictionary: 사전 확인 필요(팀원이 고친 사전의 어긋난 항목 — 추출은 계속함)."""
    out = [f"✅ {dag_label} 완료"] + [f"• {name}: {value}" for name, value in rows]
    if budget:
        out.append(f"⚠️ 비용 상한 ${budget['limit']:.2f} 도달로 LLM 추출 멈춤 · 남은 공고 {budget['left']}건은 다음 실행 때")
    if dictionary:
        out.append(f"⚠️ 사전 확인 필요 {len(dictionary)}건 (추출은 계속함)")
        out += [f"• {p}" for p in dictionary[:SHOW]]
        if len(dictionary) > SHOW:
            out.append(f"…외 {len(dictionary) - SHOW}건")
    items = [(what, no, why) for what, xs in (skipped or {}).items() for no, why in xs]
    if items:
        out.append(f"⚠️ 넘어간 공고 {len(items)}건 — 다음 실행 때 다시 시도")
        out += [f"• <{POSTING_URL.format(no=no)}|{no}> {what}" + (f" · {why}" if why else "") for what, no, why in items[:SHOW]]
        if len(items) > SHOW:
            out.append(f"…외 {len(items) - SHOW}건")
    return "\n".join(out)


def msg_failure(dag_id: str, task_id: str, try_number: int, exc: BaseException | None) -> str:
    head = f"❌ {dag_id} · {task_id} 실패 ({try_number}번째 시도)"
    if isinstance(exc, PostingsFailed):
        return f"{head} · {exc}\n{posting_lines(exc.items)}"
    return head if exc is None else f"{head} · {type(exc).__name__}: {str(exc)[:200]}"


def on_failure(context: dict) -> None:
    """Airflow on_failure_callback: 재시도까지 다 실패한 태스크를 알린다."""
    ti = context["ti"]
    send(msg_failure(ti.dag_id, ti.task_id, ti.try_number, context.get("exception")))
