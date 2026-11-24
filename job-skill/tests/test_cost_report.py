"""aws/cost_report_lambda.py — 매일 그저께 AWS 비용 Slack 리포트(가짜 비용 탐색기 응답, 진짜 AWS·Slack 에 요청하지 않음)."""
from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

from conftest import HERE

sys.path.insert(0, os.path.join(HERE, "aws"))


def day(date, groups):
    """비용 탐색기 응답의 하루치. groups = {서비스 이름: 금액}."""
    return {"TimePeriod": {"Start": date, "End": date}, "Groups": [
        {"Keys": [k], "Metrics": {"UnblendedCost": {"Amount": str(v), "Unit": "USD"}}} for k, v in groups.items()]}


RESP = {"ResultsByTime": [
    day("2026-10-28", {"Amazon Relational Database Service": 0.40, "Amazon Elastic Compute Cloud - Compute": 0.10}),
    day("2026-10-29", {"Amazon Relational Database Service": 0.312, "Amazon Elastic Compute Cloud - Compute": 0.094,
                       "Amazon Virtual Private Cloud": 0.12, "AWS Cost Explorer": 0.01, "Tax": 0.0001}),
]}


class FakeCE:
    def __init__(self, resp=RESP, error=None):
        self.resp, self.error, self.kw = resp, error, None

    def get_cost_and_usage(self, **kw):
        self.kw = kw
        if self.error:
            raise self.error
        return self.resp


NOW = dt.datetime(2026, 10, 30, 0, 5, tzinfo=dt.timezone.utc)   # 한국 시간 10/30 09:05


def test_report_message():
    """10/30 09:05 에는 그저께(10/28) 하루와 10월 1~28일 누적 — 어제(10/29) 몫은 아직 덜 정리돼 넣지 않는다
    (2026-11-07 사용자: 9시에 어제 비용을 보면 일부만 잡혀 하루 비용 합과 누적이 안 맞았음)."""
    import cost_report_lambda as c
    sent = []
    c.lambda_handler({}, None, client=FakeCE(), send=sent.append, now=NOW)
    assert sent == ["☁️ 10월 28일(그저께) AWS 비용 $0.50 (RDS $0.40 · EC2 $0.10) "
                    "· 10월 누적(1~28일) $0.50 · 프리 플랜 크레딧에서 차감"]


def test_one_query_for_two_days_ago_and_month():
    """조회는 한 번($0.01): 그 달 1일 ~ 그저께(UTC, End 는 다음 날), 하루 단위·서비스별, 크레딧·환불은 빼고."""
    import cost_report_lambda as c
    ce = FakeCE()
    c.lambda_handler({}, None, client=ce, send=lambda t: None, now=NOW)
    assert ce.kw["TimePeriod"] == {"Start": "2026-10-01", "End": "2026-10-29"}
    assert ce.kw["Granularity"] == "DAILY" and ce.kw["GroupBy"] == [{"Type": "DIMENSION", "Key": "SERVICE"}]
    assert ce.kw["Filter"] == {"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}}


def test_first_days_of_month():
    """11/2 에는 10/31 하루와 10월 전체, 11/3 에는 11/1 하루와 11월 1일 누적."""
    import cost_report_lambda as c
    ce = FakeCE({"ResultsByTime": [day("2026-10-31", {"Amazon Relational Database Service": 0.3})]})
    sent = []
    c.lambda_handler({}, None, client=ce, send=sent.append, now=dt.datetime(2026, 11, 2, 0, 5, tzinfo=dt.timezone.utc))
    assert ce.kw["TimePeriod"] == {"Start": "2026-10-01", "End": "2026-11-01"}
    assert sent[0].startswith("☁️ 10월 31일(그저께) AWS 비용 $0.30 (RDS $0.30) · 10월 누적(1~31일) $0.30")
    ce = FakeCE({"ResultsByTime": [day("2026-11-01", {"Amazon Relational Database Service": 0.2})]})
    c.lambda_handler({}, None, client=ce, send=sent.append, now=dt.datetime(2026, 11, 3, 0, 5, tzinfo=dt.timezone.utc))
    assert ce.kw["TimePeriod"] == {"Start": "2026-11-01", "End": "2026-11-02"}
    assert "· 11월 누적(1일) $0.20 ·" in sent[1]


def test_query_failure_is_reported():
    """조회가 실패하면(데이터가 아직 없음·권한 없음) 실패를 Slack 으로 알리고 Lambda 도 실패로 끝난다."""
    import cost_report_lambda as c
    sent = []
    with pytest.raises(RuntimeError):
        c.lambda_handler({}, None, client=FakeCE(error=RuntimeError("DataUnavailableException")), send=sent.append, now=NOW)
    assert len(sent) == 1 and sent[0].startswith("⚠️ AWS 비용 조회 실패") and "DataUnavailableException" in sent[0]
