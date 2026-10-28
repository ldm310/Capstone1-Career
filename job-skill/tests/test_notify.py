"""notify.py — Slack 알림 시험. 실제 Slack 으로는 보내지 않는다(urlopen 을 가짜로)."""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

import pytest


def test_msg_result_format():
    import notify
    assert notify.msg_result("매일 수집", {"새 공고": 52, "추출": 52, "확인 필요": 2, "오늘 비용": 0.214}) == \
        "✅ 매일 수집 완료 · 새 공고 52 · 추출 52 · 확인 필요 2 · 오늘 비용 $0.21"


def test_msg_failure_truncates():
    import notify
    msg = notify.msg_failure("daily_collect", "collect_list", 3, RuntimeError("가" * 500))
    assert msg.startswith("❌ daily_collect · collect_list 실패 (3번째 시도) · RuntimeError: ")
    assert msg.endswith("가" * 200) and "가" * 201 not in msg
    assert notify.msg_failure("d", "t", 1, None) == "❌ d · t 실패 (1번째 시도)"


def test_msg_budget_and_daily_cost():
    import notify
    m = notify.msg_budget("매일 수집", 5.02, 5.0, 12)
    assert "$5.00" in m and "$5.02" in m and "12건" in m and m.startswith("⚠️ 매일 수집:")
    assert notify.msg_daily_cost(dt.date(2026, 10, 27), 0.413, 104) == "💰 10월 27일 LLM 비용 $0.41 (추출 104건)"


def test_send_posts_json_to_webhook(monkeypatch):
    import notify
    seen = {}

    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"ok"

    def fake_urlopen(req, timeout=0):
        seen["url"], seen["body"] = req.full_url, json.loads(req.data.decode("utf-8"))
        return Resp()

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/TEST/TEST/TEST")
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    assert notify.send("시험 메시지") is True
    assert seen == {"url": "https://hooks.slack.com/services/TEST/TEST/TEST", "body": {"text": "시험 메시지"}}


def test_send_without_webhook_returns_false(monkeypatch, tmp_path):
    import notify
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(notify, "ENV_PATH", str(tmp_path / ".env"))
    assert notify.send("보내지면 안 됨") is False


def test_on_failure_sends_task_failure(monkeypatch):
    import notify
    sent = []
    monkeypatch.setattr(notify, "send", lambda text: sent.append(text) or True)
    ti = SimpleNamespace(dag_id="daily_collect", task_id="load_db", try_number=3)
    notify.on_failure({"ti": ti, "exception": ValueError("DB 접속 실패")})
    assert sent == ["❌ daily_collect · load_db 실패 (3번째 시도) · ValueError: DB 접속 실패"]
