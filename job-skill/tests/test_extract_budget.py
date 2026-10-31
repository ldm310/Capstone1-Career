"""extract_skills.run_model 비용 상한(max_usd)과 입력 0건 처리 시험 — 가짜 LLM(돈 안 듦)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import HERE

pytestmark = pytest.mark.usefixtures("use_seed_dictionary")   # 추출은 DB 사전을 쓴다

MODEL, TAG = "gpt-5.6-luna", "-ex"
ANSWER = {"positions": [{"name": "서버 개발자", "it_job": True, "career": "신입", "years": "",
                         "required": [{"text": "Java 개발 경험", "quote": "Java 개발 경험",
                                       "reqs": [{"capability": "프로그래밍 언어", "other_name": "", "techs": ["Java"],
                                                 "relation": "모두"}]}],
                         "preferred": [], "duties": [], "other": []}], "skipped": [], "notes": ""}


class FakeClient:
    """호출마다 입력 10,000 / 출력 1,000 토큰 = luna 기준 $0.0032."""

    def __init__(self):
        self.calls = 0
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls += 1
        return SimpleNamespace(output_text=json.dumps(ANSWER, ensure_ascii=False), status="completed",
                               usage=SimpleNamespace(input_tokens=10000, output_tokens=1000))


def inputs(n):
    return {f"T{i}": {"role": "백엔드", "company": "(주)지어낸회사", "career": "", "text": "서버 개발자 모집\nJava 개발 경험"}
            for i in range(1, n + 1)}


@pytest.fixture
def ex(tmp_path, monkeypatch):
    import extract_skills
    monkeypatch.setattr(extract_skills, "EX", str(tmp_path))
    return extract_skills


def test_stops_before_exceeding_budget(ex, tmp_path):
    client = FakeClient()
    stats = ex.run_model(client, MODEL, "low", inputs(5), examples=True, tag=TAG, max_usd=0.006)
    assert client.calls == 2
    assert stats["stopped"] is True and stats["left"] == 3
    assert round(stats["spent_new"], 6) == 0.0064
    budget = json.loads((tmp_path / "_budget.json").read_text(encoding="utf-8"))
    assert budget == {"stopped": True, "spent": 0.0064, "limit": 0.006, "left": 3}


def test_no_budget_runs_all(ex, tmp_path):
    client = FakeClient()
    stats = ex.run_model(client, MODEL, "low", inputs(5), examples=True, tag=TAG, max_usd=None)
    assert client.calls == 5 and stats["stopped"] is False and stats["left"] == 0
    assert not (tmp_path / "_budget.json").exists()


def test_cached_results_cost_nothing(ex, tmp_path):
    d = tmp_path / (MODEL + TAG)
    d.mkdir()
    for i in (1, 2, 3):   # 이미 결과가 있는 공고: 비용 없이 건너뜀
        (d / f"T{i}.json").write_text(json.dumps({"rec_idx": f"T{i}", "input_tokens": 9, "output_tokens": 9, "seconds": 0,
                                                  "positions": [], "rejected": [], "excluded": [], "review_reasons": []}),
                                      encoding="utf-8")
    client = FakeClient()
    stats = ex.run_model(client, MODEL, "low", inputs(6), examples=True, tag=TAG, max_usd=0.004)
    assert client.calls == 2                       # T4($0.0032 < 0.004) → T5($0.0064) → T6 전에 멈춤
    assert stats["stopped"] is True and stats["left"] == 1


def test_main_with_zero_inputs_exits_cleanly(tmp_path):
    (tmp_path / "targets.tsv").write_text("rec_idx\tcompany\ttitle\trole\tcareer\tdeadline\tkind\ttext_chars\timages\n",
                                          encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    env.update({"OCR_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"})
    r = subprocess.run([sys.executable, "extract_skills.py", "--models", MODEL, "--examples", f"--tag={TAG}", "--max-usd", "1"],
                       cwd=HERE, env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads((tmp_path / "out" / "extract" / "_stats.json").read_text(encoding="utf-8")) == []


class FlakyClient(FakeClient):
    """bad 번째 호출에서 예외(응답 잘림·거절·잘못된 요청 흉내)."""

    def __init__(self, bad):
        super().__init__()
        self.bad = set(bad)

    def _create(self, **kw):
        if self.calls + 1 in self.bad:
            self.calls += 1
            raise RuntimeError("지어낸 LLM 오류")
        return super()._create(**kw)


def test_one_bad_posting_does_not_stop_the_run(ex, tmp_path):
    """공고 하나가 실패해도 나머지는 추출·저장된다(실패한 공고는 결과 없이 저장 → 다음 ① 의 밀린 공고)."""
    stats = ex.run_model(FlakyClient(bad={2}), MODEL, "low", inputs(3), examples=True, tag=TAG)
    d = tmp_path / (MODEL + TAG)
    assert sorted(p.name for p in d.glob("*.json")) == ["T1.json", "T3.json"]
    assert stats["failed"] == ["T2"]


def test_all_postings_failing_raises(ex):
    """전부 실패하면(키 오류·연결 끊김 등) 태스크를 실패시켜 Slack 으로 알린다."""
    with pytest.raises(RuntimeError):
        ex.run_model(FlakyClient(bad={1, 2, 3}), MODEL, "low", inputs(3), examples=True, tag=TAG)


class BrokenJsonClient(FakeClient):
    """두 번째 호출의 답이 잘려 JSON 이 아님(응답 길이 상한에 걸린 경우 흉내)."""

    def _create(self, **kw):
        r = super()._create(**kw)
        if self.calls == 2:
            r.output_text = '{"positions": [{"name": "서버 개발'
        return r


def test_failure_reasons_are_counted(ex):
    """실패한 공고 수와 원인을 센다(Slack 알림용 — 공고 내용·번호는 넣지 않음)."""
    stats = ex.run_model(BrokenJsonClient(), MODEL, "low", inputs(3), examples=True, tag=TAG)
    assert stats["failed"] == ["T2"] and stats["fail_reasons"] == {"응답 잘림·형식 오류": 1}
    assert stats["fail_detail"] == {"T2": "응답 잘림·형식 오류"}
    stats = ex.run_model(FlakyClient(bad={1}), MODEL, "low", inputs(2), examples=True, tag=TAG + "2")
    assert stats["fail_reasons"] == {"RuntimeError": 1}


class RecordingClient(FakeClient):
    """호출 인자를 남긴다."""

    def _create(self, **kw):
        self.kw = kw
        return super()._create(**kw)


def test_output_cap_fits_long_postings(ex):
    """답 길이 상한 16,000 토큰 — 8,000 이면 모집 부문이 많은 긴 공고(③에서 7건)의 답이 중간에 잘렸다."""
    client = RecordingClient()
    ex.call_llm(client, MODEL, "low", inputs(1)["T1"], examples=True)
    assert client.kw["max_output_tokens"] == 16000


# ── 동시에 여러 공고(workers) ──────────────────────────────────────────────
import threading


class ParallelClient(FakeClient):
    """여러 스레드에서 불려도 호출 수를 정확히 센다. bad_tag 가 들어간 공고는 예외."""

    def __init__(self, bad_tag=None):
        super().__init__()
        self.lock, self.bad_tag, self.peak, self.now = threading.Lock(), bad_tag, 0, 0

    def _create(self, **kw):
        import time
        with self.lock:
            self.calls += 1
            self.now += 1
            self.peak = max(self.peak, self.now)
        try:
            time.sleep(0.05)                                     # 동시에 돌고 있는지 보이게
            if self.bad_tag and self.bad_tag in str(kw):
                raise RuntimeError("지어낸 LLM 오류")
            return SimpleNamespace(output_text=json.dumps(ANSWER, ensure_ascii=False), status="completed",
                                   usage=SimpleNamespace(input_tokens=10000, output_tokens=1000))
        finally:
            with self.lock:
                self.now -= 1


def tagged(n):
    return {f"T{i}": {"role": "백엔드", "company": "(주)지어낸회사", "career": "", "text": f"서버 개발자 모집 공고{i}번\nJava 개발 경험"}
            for i in range(1, n + 1)}


def test_workers_extract_all_in_parallel(ex, tmp_path):
    client = ParallelClient()
    stats = ex.run_model(client, MODEL, "low", tagged(8), examples=True, tag=TAG, workers=4)
    assert client.calls == 8 and len(list((tmp_path / (MODEL + TAG)).glob("*.json"))) == 8
    assert client.peak == 4 and stats["done_new"] == 8                       # 실제로 4건씩 동시에


def test_workers_budget_overshoot_is_bounded(ex, tmp_path):
    """동시에 부르면 상한을 넘는 폭은 '이미 부른 건수(workers-1)'까지."""
    client = ParallelClient()
    stats = ex.run_model(client, MODEL, "low", tagged(9), examples=True, tag=TAG, max_usd=0.006, workers=4)
    assert stats["stopped"] is True and 2 <= client.calls <= 2 + 3
    assert stats["left"] == 9 - client.calls
    assert len(list((tmp_path / (MODEL + TAG)).glob("*.json"))) == client.calls


def test_workers_failure_skips_only_that_posting(ex, tmp_path):
    stats = ex.run_model(ParallelClient(bad_tag="공고3번"), MODEL, "low", tagged(6), examples=True, tag=TAG, workers=3)
    assert stats["failed"] == ["T3"] and stats["done_new"] == 5
