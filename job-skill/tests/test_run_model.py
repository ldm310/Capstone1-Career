"""extract_skills.run_model — 다시 부르기·확인 필요 사유·표준화 전 답 저장 시험 (가짜 LLM, 돈 안 듦)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def unit(name, career, years, req_text, techs):
    return {"name": name, "it_job": True, "career": career, "years": years,
            "required": [{"text": req_text, "quote": req_text,
                          "reqs": [{"capability": "프로그래밍 언어", "other_name": "", "techs": techs, "relation": "모두"}]}],
            "preferred": [], "duties": [], "other": []}


FIRST = {"positions": [unit("서버 개발자", "신입", "", "Java 개발 경험", ["Java"])], "skipped": [], "notes": ""}
SECOND = {"positions": [unit("서버 개발자 (신입)", "신입", "", "Java 개발 경험", ["Java"]),
                        unit("서버 개발자 (경력)", "경력", "3년 이상", "Java 개발 경력 3년 이상", ["Java"])],
          "skipped": [], "notes": ""}
INPUT = {"role": "백엔드", "company": "(주)예시소프트", "career": "신입 · 경력 · 정규직",
         "text": "서버 개발자 모집\n신입: Java 개발 경험\n경력: Java 개발 경력 3년 이상"}


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw["input"])
        body = FIRST if len(self.calls) == 1 else SECOND
        return SimpleNamespace(output_text=json.dumps(body, ensure_ascii=False), status="completed",
                               usage=SimpleNamespace(input_tokens=10000, output_tokens=1000))


@pytest.fixture
def result(tmp_path, monkeypatch):
    import extract_skills as ex
    monkeypatch.setattr(ex, "EX", str(tmp_path))
    client = SimpleNamespace(responses=FakeResponses())
    ex.run_model(client, "gpt-5.6-luna", "low", {"T1": INPUT}, examples=True, tag="-test")
    r = json.load(open(tmp_path / "gpt-5.6-luna-test" / "T1.json", encoding="utf-8"))
    return client, r


def test_retry_with_hint_fixes_missing_career(result):
    client, r = result
    assert len(client.responses.calls) == 2
    assert "[다시 확인]" in client.responses.calls[1] and "신입 · 경력" in client.responses.calls[1]
    assert r["checks"]["used"] == "retry"
    assert r["checks"]["first"] == [{"검사": 1, "내용": "경력 조건 '신입 · 경력 · 정규직' / 만든 자리 경력: 신입"}]
    assert r["review_reasons"] == []


def test_raw_answer_saved_before_standardization(result):
    _, r = result
    assert len(r["llm_output_raw"]["positions"]) == 2
    assert r["llm_output_raw"]["positions"][0]["required"][0]["reqs"][0]["techs"] == ["Java"]     # 표준화 전: 글자
    assert r["positions"][0]["required"][0]["reqs"][0]["techs"][0]["kind"] == "tech"            # 표준화 후: 사전 항목


def test_run_records_versions_and_cost(result):
    _, r = result
    assert len(r["prompt_version"]) == 12 and len(r["dict_version"]) == 12 and len(r["input_hash"]) == 64
    assert (r["input_tokens"], r["output_tokens"]) == (20000, 2000)
    assert r["cost_usd"] == 0.0064


def test_old_check_flag_is_converted():
    import extract_skills as ex
    old = {"check_flag": ["사람인 목록상 이 공고의 경력 조건은 '신입'이다. …"], "positions": [], "rejected": []}
    assert ex.review_reasons(old) == [{"검사": 1, "내용": "사람인 목록상 이 공고의 경력 조건은 '신입'이다. …"}]
