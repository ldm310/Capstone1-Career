"""단락 거르기(section_split.decide) — 자격요건·우대사항·담당업무 단락은 꼭 남긴다(빠지면 안 됨, 사용자 결정 2026-11-01).
LLM 에 보내기 전 단계만 본다(LLM 호출 없음)."""
from __future__ import annotations

import pytest

import section_split as ss


@pytest.mark.parametrize("text", [
    "자격요건\n- 컴퓨터공학 전공 또는 이에 준하는 지식",
    "우대사항\n- 대용량 트래픽 처리 경험",
    "담당업무\n- 사내 서비스 API 개발 및 운영",
    "자 격 요 건\n- 관련 학과 졸업",                     # OCR 이 음절마다 띄어 쓴 경우
    "필수\n- 원활한 의사소통",
    "Java, Spring Boot 로 서비스 개발",                  # 머리말 없이 기술 이름만
    "자격요건 및 복리후생\n- 4대보험, 학자금 지원",       # 복지 낱말이 섞여도 요건 낱말이 있으면 남김
])
def test_requirement_paragraphs_are_kept(text):
    assert ss.decide(text)["decision"] == "남기기"


def test_benefit_only_paragraph_is_dropped():
    assert ss.decide("복리후생\n- 4대보험, 연차, 경조사 지원, 건강검진, 사내 카페, 자율 출퇴근")["decision"] == "빼기"
