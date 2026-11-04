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


def test_null_alias_does_not_break_prompt(db):
    db.execute("UPDATE capability SET aliases = array_prepend(NULL::text, aliases) WHERE name = '디버깅·트러블슈팅'")   # 지시문은 앞의 3개를 씀
    ex.prepare_dictionary(db)
    assert "- 디버깅·트러블슈팅 — = 디버깅, Debugging, 트러블슈팅" in ex.instructions().splitlines()


def _extract_with_real_report(db, tmp_path, monkeypatch):
    """Airflow 추출 태스크가 진짜 추출 스크립트의 쪽지(_dictionary.json)를 읽게: 가짜 실행이 write_dictionary_report 를 부른다."""
    import subprocess
    import pipeline_tasks
    from test_pipeline_tasks import write_rows
    write_rows(tmp_path, ["A"])
    out = tmp_path / "out" / "extract"
    out.mkdir(parents=True)

    def fake_run(script, args, run_dir, **k):
        if ex.write_dictionary_report(db, str(out))["fatal"]:
            raise subprocess.CalledProcessError(1, [script])
        (out / "_stats.json").write_text('[{"failed": [], "fail_reasons": {}}]', encoding="utf-8")

    monkeypatch.setattr(pipeline_tasks, "run_script", fake_run)
    return pipeline_tasks.step_extract(str(tmp_path), budget_usd=5.0, limit=5.0)


def test_real_report_stops_task_with_reason(db, tmp_path, monkeypatch):
    db.execute("UPDATE capability SET is_active = false WHERE name = '기타'")
    with pytest.raises(RuntimeError, match="사전이 망가져 추출을 멈춤: '기타' 능력이 없거나 꺼짐"):
        _extract_with_real_report(db, tmp_path, monkeypatch)


def test_real_report_problems_reach_result_alert(db, tmp_path, monkeypatch):
    import json
    db.execute("UPDATE tech SET aliases = aliases || '{aws}' WHERE name = 'Lambda'")
    _extract_with_real_report(db, tmp_path, monkeypatch)
    notes = json.load(open(tmp_path / "alerts.json", encoding="utf-8"))["사전 확인 필요"]
    assert any("AWS" in p and "Lambda" in p for p in notes)
