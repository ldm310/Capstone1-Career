"""
매일 그저께 AWS 비용을 Slack 으로 보내는 AWS Lambda (AWS 브랜치).

EventBridge 스케줄러가 매일 09:00(서울)에 부른다. AWS 의 하루는 UTC 0~24시(= 한국 시간 그날 09:00 ~ 다음 날 09:00)다.
비용 탐색기(Cost Explorer) 숫자는 하루쯤 늦게 채워져서, 09:00 에 막 끝난 어제 몫을 보면 일부만 잡힌다
→ 하루 비용 합과 누적이 안 맞았다(2026-11-07 사용자). 그래서 거의 확정된 그저께 하루와 그 달 1일~그저께 누적을 보낸다.

- 조회는 한 번(1번에 $0.01): 그 달 1일 ~ 그저께(UTC), 하루 단위·서비스별, 크레딧·환불은 뺀 실제 사용 금액
- Lambda 설정: 런타임 Python 3.12+, 환경변수 SLACK_WEBHOOK_URL, 실행 역할에 ce:GetCostAndUsage 권한
- 이 파일 하나를 Lambda 코드 편집기에 그대로 붙여 넣는다(boto3 는 Lambda 에 들어 있음). 핸들러: lambda_function.lambda_handler
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request

SHORT = {  # 메시지에 따로 적을 서비스(나머지는 '기타')
    "Amazon Relational Database Service": "RDS",
    "Amazon Elastic Compute Cloud - Compute": "EC2",
    "EC2 - Other": "EC2",
    "Amazon Virtual Private Cloud": "공인 IP",
}


def slack(text: str) -> None:
    req = urllib.request.Request(os.environ["SLACK_WEBHOOK_URL"], data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()


def _amounts(result: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for g in result.get("Groups", []):
        name = SHORT.get(g["Keys"][0], "기타")
        out[name] = out.get(name, 0.0) + float(g["Metrics"]["UnblendedCost"]["Amount"])
    return out


def message(day: dt.date, by: dict[str, float], month_total: float) -> str:
    """'☁️ 10월 28일(그저께) AWS 비용 $0.50 (RDS $0.40 · EC2 $0.10) · 10월 누적(1~28일) $0.50 · 프리 플랜 크레딧에서 차감'."""
    parts = [f"{k} ${v:.2f}" for k, v in sorted(by.items(), key=lambda kv: (kv[0] == "기타", -kv[1])) if v >= 0.005]
    detail = f" ({' · '.join(parts)})" if parts else ""
    days = "1일" if day.day == 1 else f"1~{day.day}일"
    return (f"☁️ {day.month}월 {day.day}일(그저께) AWS 비용 ${sum(by.values()):.2f}{detail} "
            f"· {day.month}월 누적({days}) ${month_total:.2f} · 프리 플랜 크레딧에서 차감")


def lambda_handler(event, context, client=None, send=None, now: dt.datetime | None = None):
    send = send or slack
    today = (now or dt.datetime.now(dt.timezone.utc)).date()
    day = today - dt.timedelta(days=2)   # 그저께 — 어제 몫은 아직 덜 채워져 있다
    if client is None:
        import boto3
        client = boto3.client("ce", region_name="us-east-1")   # 비용 탐색기는 us-east-1 끝점
    try:
        resp = client.get_cost_and_usage(
            TimePeriod={"Start": str(day.replace(day=1)), "End": str(day + dt.timedelta(days=1))}, Granularity="DAILY",
            Metrics=["UnblendedCost"], GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            Filter={"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}})
    except Exception as e:  # 데이터가 아직 없음·권한 없음 등 — 알리고 Lambda 도 실패로 끝낸다
        send(f"⚠️ AWS 비용 조회 실패: {type(e).__name__}: {str(e)[:200]}")
        raise
    results = [r for r in resp.get("ResultsByTime", []) if r["TimePeriod"]["Start"] <= str(day)]   # 그 달 1일 ~ 그저께
    month_total = sum(sum(_amounts(r).values()) for r in results)
    yesterday = next((r for r in results if r["TimePeriod"]["Start"] == str(day)), {})
    text = message(day, _amounts(yesterday), month_total)
    send(text)
    return {"text": text}
