"""extract_skills.run_model 비용 상한(max_usd)과 입력 0건 처리 시험 — 가짜 LLM(돈 안 듦)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import HERE

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
