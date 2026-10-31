"""extract_skills — 추출을 시작할 때 DB 사전을 읽는다(팀원이 고친 사전이 다음 추출부터), 망가진 사전이면 멈춘다."""
from __future__ import annotations

import pytest

import extract_skills as ex

pytestmark = pytest.mark.usefixtures("use_seed_dictionary")   # 끝나면 시드 사전으로 되돌림


def test_prepare_dictionary_stops_on_broken_dictionary(db):
    db.execute("UPDATE capability SET is_active = false WHERE name = '기타'")
    with pytest.raises(ex.DictionaryBroken, match="기타") as e:
        ex.prepare_dictionary(db)
    assert e.value.reasons == ["'기타' 능력이 없거나 꺼짐"]


def test_teammate_alias_is_used_in_next_extraction(db):
    assert ex.prepare_dictionary(db)[0].lookup("스프링부트3")["kind"] == "unknown"     # 고치기 전
    db.execute("UPDATE tech SET aliases = aliases || '{스프링부트3}' WHERE name = 'Spring Boot'")
    cd, problems = ex.prepare_dictionary(db)
    assert cd.lookup("스프링부트3")["name"] == "Spring Boot" and problems == []
    assert ex.CD is cd


def test_enum_follows_dictionary(db):
    db.execute("INSERT INTO capability (name) VALUES ('시험능력')")
    ex.prepare_dictionary(db)
    assert "시험능력" in ex.REQ["properties"]["capability"]["enum"]
    assert ex.REQ["properties"]["capability"]["enum"].count("기타") == 1
    assert "- 시험능력" in ex.instructions().splitlines()
