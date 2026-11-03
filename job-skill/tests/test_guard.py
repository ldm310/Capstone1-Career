"""extract_skills.guard — LLM 이 적은 기술 이름을 사전으로 정리하는 규칙(가짜 LLM 답, 시드 사전)."""
from __future__ import annotations

import pytest

import extract_skills as ex

pytestmark = pytest.mark.usefixtures("use_seed_dictionary")

TEXT = "자격요건: Java, Kubernetes(K8s), AI 활용, Claude 사용 경험, HTML/CSS 퍼블리싱, 원활한 소통"


def run(cat, *reqs):
    pos = {"name": "백엔드", "it_job": True, "career": "신입", "years": "", "required": [], "preferred": [], "duties": [], "other": []}
    pos[cat] = [{"text": "지어낸 줄", "quote": "Java", "reqs": [dict(capability=c, other_name=o, techs=t, relation=r) for c, o, t, r in reqs]}]
    out = ex.guard({"positions": [pos], "skipped": [], "notes": ""}, TEXT)
    return out, out["positions"][0][cat]


def test_name_not_in_posting_is_dropped():          # 1. 공고 글에 없는 이름(지어냈을 수 있음)
    out, items = run("required", ("메시지 브로커", "", ["Kafka"], "예시"), ("프로그래밍 언어", "", ["Java"], "예시"))
    assert [r["capability"] for r in items[0]["reqs"]] == ["프로그래밍 언어"] and out["rejected"][0]["name"] == "Kafka"


def test_llm_model_name_is_excluded():              # 2. LLM 모델 이름
    out, items = run("required", ("프로그래밍 언어", "", ["Java", "Claude"], "예시"))
    assert [e["name"] for e in items[0]["reqs"][0]["techs"]] == ["Java"]
    assert out["excluded"][0]["reason"] == "LLM 모델 이름"


def test_generic_word_keeps_requirement_as_capability_only():   # 3. 일반 낱말은 낱말만 빼고 요건은 남김
    _, items = run("required", ("머신러닝", "", ["AI"], "예시"))
    assert items[0]["reqs"][0]["techs"] == [] and items[0]["reqs"][0]["relation"] == "능력만"


def test_combined_name_is_split():                  # 4. 묶인 표기 나누기
    _, items = run("required", ("컨테이너 오케스트레이션", "", ["Kubernetes(K8s)"], "예시"))
    assert [e["name"] for e in items[0]["reqs"][0]["techs"]] == ["Kubernetes"]


def test_other_with_tech_name_links_to_dictionary_capability():   # 5. 기타 + 기술 이름 → 사전 능력
    _, items = run("required", ("기타", "HTML/CSS", [], "능력만"))
    assert items[0]["reqs"][0]["capability"] == "프론트엔드 프레임워크" and items[0]["reqs"][0]["cap_ok"]


def test_other_line_without_concrete_tech_is_dropped():          # 6. 구체적인 기술이 없는 기타 칸 줄
    out, items = run("other", ("기타", "원활한 소통", [], "능력만"))
    assert items == [] and out["dropped_items"][0]["from"] == "other"
