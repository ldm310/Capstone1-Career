"""지시문(instructions)에 사용자가 정한 규칙이 들어 있는지."""
from __future__ import annotations

import pytest

import extract_skills as ex

pytestmark = pytest.mark.usefixtures("use_seed_dictionary")   # 지시문의 능력 목록은 DB 사전에서


def relation_line(name: str) -> str:
    """관계 하나의 설명(이어지는 줄 포함 — 이어지는 줄은 '—' 뒤 글자에 맞춰 더 들여 씀)."""
    lines = ex.instructions().splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.strip().startswith(name + " "))
    indent = len(lines[i]) - len(lines[i].lstrip())
    out = [lines[i]]
    for ln in lines[i + 1:]:
        if len(ln) - len(ln.lstrip()) <= indent:
            break
        out.append(ln)
    return " ".join(s.strip() for s in out)


def test_slash_means_all():
    """빗금(/)으로 묶인 기술은 모두 필요(2026-10-29 사용자 결정 — 'Linux/Unix', 'C/C++')."""
    line = relation_line("모두")
    assert "빗금(/)" in line and "Linux/Unix" in line


def test_choice_words_mean_one_of():
    """고르라는 말('또는', '혹은', 'or')이 있을 때만 택1."""
    line = relation_line("택1")
    for w in ("'또는'", "'혹은'", "'or'"):
        assert w in line


def test_examples_are_only_examples():
    """예시 답안의 능력 이름이 사전과 달라도 목록을 따른다(예시는 코드에 고정, 목록은 DB 사전)."""
    assert "능력 이름은 위 '능력 목록'에 있는 것만 쓰고, 예시와 다르면 목록을 따른다" in ex.instructions(examples=True)
