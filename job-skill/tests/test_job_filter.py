"""직무 거르기 — 백엔드·데이터 엔지니어 자리만 필수·우대·업무를 정리한다(2026-11-12 사용자 결정, 그 외 직무는 버리는 데이터).
자리 이름이 아니라 업무 내용으로 판단하고, 풀스택은 서버·API 개발이 들어가면 백엔드다."""
from __future__ import annotations

import pytest

import extract_skills as ex
from test_insert_run import _insert, item, req, tech
from test_db_queries import add_posting


def pos(name, job, it_job=True, **items):
    p = {"name": name, "it_job": it_job, "job": job, "career": "신입", "years": "",
         "required": [], "preferred": [], "duties": [], "other": []}
    p.update(items)
    return p


def test_only_backend_and_data_engineer_are_targets():
    assert ex.target_job(pos("서버", "백엔드")) and ex.target_job(pos("ETL", "데이터 엔지니어"))
    assert not ex.target_job(pos("프론트", "그 외"))
    assert not ex.target_job(pos("회계", "백엔드", it_job=False))          # IT 가 아니면 직무가 뭐든 아님
    old = pos("옛 결과", "백엔드")
    del old["job"]                                                         # job 칸이 없는 옛 결과는 IT 면 대상
    assert ex.target_job(old) and not ex.target_job({**old, "it_job": False})


def test_job_is_judged_by_content_and_fullstack_is_backend():
    rule = ex.JOB_RULE
    assert "자리 이름만 보지 말고" in rule and "풀스택" in rule and "백엔드다" in rule
    assert "AI 에이전트 개발" in rule and "섞여 있어도 그 외" in rule          # AI 자리는 빼기(2026-11-12 사용자 결정)
    assert ex.POSITION["properties"]["job"]["enum"] == ["백엔드", "데이터 엔지니어", "그 외"] and "job" in ex.POSITION["required"]
    assert "{JOB_RULE}" not in ex.INSTRUCTIONS and rule in ex.INSTRUCTIONS


def test_empty_other_job_is_not_a_check_failure():
    """검사 3(내용이 비었음)은 백엔드·데이터 엔지니어 자리만 본다 — '그 외'는 원래 비운다."""
    r = {"positions": [pos("프론트엔드", "그 외"), pos("서버 개발", "백엔드")]}
    found = ex.unit_checks(r, {"career": "", "text": ""})
    assert [(f["검사"], f["내용"]) for f in found] == [(3, "백엔드 자리 '서버 개발'의 필수·우대·업무가 비어 있음")]


@pytest.mark.usefixtures("use_seed_dictionary")
def test_guard_empties_other_job_positions():
    """LLM 이 '그 외' 자리에 줄을 적었어도 비운다. IT 가 아닌 자리는 직무를 '그 외'로 맞춘다."""
    line = {"text": "Java 개발", "quote": "Java", "reqs": [{"capability": "프로그래밍 언어", "other_name": "", "techs": ["Java"], "relation": "모두"}]}
    out = ex.guard({"positions": [pos("앱 개발", "그 외", required=[dict(line)]), pos("회계", "백엔드", it_job=False),
                                  pos("서버", "백엔드", required=[dict(line)])], "skipped": [], "notes": ""}, "Java")
    assert [(p["job"], len(p["required"])) for p in out["positions"]] == [("그 외", 0), ("그 외", 0), ("백엔드", 1)]


def test_job_is_saved_and_other_job_has_no_items(db, tmp_path):
    r = {"model": "gpt-5.6-luna", "prompt_version": "p" * 12, "dict_version": "d" * 12, "input_hash": "3" * 64,
         "input_tokens": 1, "output_tokens": 1,
         "positions": [pos("웹 개발자", "백엔드", required=[item("Java 경험", req("프로그래밍 언어", [tech("Java")]))]),
                       pos("플랫폼팀", "데이터 엔지니어", duties=[item("ETL 개발", req("데이터 파이프라인", relation="능력만"))]),
                       pos("앱 개발자", "그 외", required=[item("Swift 경험", req("프로그래밍 언어", [tech("Swift")]))]),
                       pos("영업", "그 외", it_job=False)]}
    _insert(db, tmp_path, add_posting(db, "J"), r)
    assert db.execute("""SELECT u.name, u.job, count(i.id) FROM recruit_unit u LEFT JOIN unit_item i ON i.unit_id = u.id
                         GROUP BY u.id ORDER BY u.seq""").fetchall() == [
        ("웹 개발자", "백엔드", 1), ("플랫폼팀", "데이터 엔지니어", 1), ("앱 개발자", "그 외", 0), ("영업", "그 외", 0)]


def test_old_result_without_job_leaves_it_unknown(db, tmp_path):
    """job 칸이 없는 옛 결과: IT 자리는 비움(fill_unit_job.py 가 채움), IT 가 아닌 자리는 '그 외'."""
    from test_insert_run import RESULT
    _insert(db, tmp_path, add_posting(db, "K"), RESULT)
    assert db.execute("SELECT name, job FROM recruit_unit ORDER BY seq").fetchall() == [("백엔드 개발자", None), ("영업 담당", "그 외")]
