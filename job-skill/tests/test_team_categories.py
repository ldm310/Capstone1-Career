"""공고 카테고리(팀원 7개판) — 줄마다 팀원 결과나 LLM 결과를 찾아 공고 단위로 기술 카테고리만 모은다(2026-11-27 사용자 결정)."""
from __future__ import annotations

import json

import pytest

import team_categories as tc
from test_insert_run import _insert, item, req, tech
from test_db_queries import add_posting


def test_norm_matches_team_api():
    """팀원 API 와 같은 맞춤: NFC + 공백 하나. 다른 글자는 그대로."""
    assert tc.norm("  Java\t·  Spring\n경험 ") == "Java · Spring 경험"
    assert tc.norm("Java 경험") != tc.norm("Java 경험 3년")


def test_load_team_reads_presentation_rows(tmp_path):
    rows = [{"text": "Java  경험", "categories": ["L"], "excluded": False},
            {"text": "협업 태도", "categories": [], "excluded": True},
            {"text": "Git 협업", "categories": ["T", "OTHER"], "excluded": False}]
    path = tmp_path / "team.html"
    path.write_text('<script type="application/json" id="presentation-data">' + json.dumps({"rows": rows}) + "</script>",
                    encoding="utf-8")
    assert tc.load_team(str(path)) == {"Java 경험": ["L"], "협업 태도": ["EXCLUDED"], "Git 협업": ["OTHER", "T"]}


def test_clean_drops_excluded_next_to_others():
    assert tc.clean(["B", "EXCLUDED", "L"]) == ["L", "B"]
    assert tc.clean(["EXCLUDED"]) == ["EXCLUDED"]


def test_posting_categories_keeps_only_tech_codes():
    """공고에는 기술 7개만 모은다. 기타·도구·업종·지원 조건·제외는 붙이지 않는다. 못 찾은 줄은 세기만 한다."""
    team = {"Java 경험": ["L"], "학사 이상": ["X"], "금융 Java 개발": ["L", "M"], "Git 협업": ["OTHER", "T"]}
    llm = {"Docker 배포": {"cats": ["O"], "unsure": False}, "소통": {"cats": ["EXCLUDED"], "unsure": True}}
    lines = [(1, "필수", "Java  경험"), (1, "필수", "학사 이상"), (1, "우대", "Docker 배포"), (1, "우대", "소통"),
             (2, "필수", "학사 이상"), (2, "우대", "Git 협업"),
             (3, "필수", "금융 Java 개발"), (3, "우대", "처음 보는 줄")]
    P = tc.posting_categories(lines, team, llm)
    assert P[1]["codes"] == {"L", "O"} and (P[1]["team"], P[1]["llm"], P[1]["unsure"]) == (2, 2, 1)
    assert P[2]["codes"] == set()                      # 지원 조건·도구뿐 → 없음
    assert P[3]["codes"] == {"L"} and P[3]["missing"] == 1


def _pos(name, job, **items):
    p = {"name": name, "it_job": True, "job": job, "career": "신입", "years": "",
         "required": [], "preferred": [], "duties": [], "other": []}
    p.update(items)
    return p


def _result(*positions):
    return {"model": "gpt-5.6-luna", "prompt_version": "p" * 12, "dict_version": "d" * 12, "input_hash": "4" * 64,
            "input_tokens": 1, "output_tokens": 1, "positions": list(positions)}


def test_save_writes_posting_categories(db, tmp_path):
    """현재 결과가 있는 공고만 쓴다. 백엔드·데이터 자리가 있는데 기술이 없으면 {}, 그 외 자리만 있으면 NULL(대상 아님),
    못 찾은 줄이 남으면 건너뛴다(비움 그대로)."""
    java = item("Java 경험", req("프로그래밍 언어", [tech("Java")]))
    docker = item("Docker 배포", req("프로그래밍 언어", [tech("Java")]))
    a, b, c, d, e = (add_posting(db, n) for n in "ABCDE")
    _insert(db, tmp_path, a, _result(_pos("서버", "백엔드", required=[java], preferred=[docker],
                                          duties=[item("모르는 업무", req("프로그래밍 언어", relation="능력만"))])))
    _insert(db, tmp_path, b, _result(_pos("앱", "그 외")))
    _insert(db, tmp_path, d, _result(_pos("데이터", "데이터 엔지니어", required=[item("처음 보는 줄", req("프로그래밍 언어", relation="능력만"))])))
    _insert(db, tmp_path, e, _result(_pos("서버", "백엔드"), _pos("앱", "그 외")))
    team, llm = {"Java 경험": ["L"]}, {"Docker 배포": {"cats": ["O"], "unsure": False}}
    P = tc.posting_categories(tc.current_lines(db), team, llm)
    assert tc.save(db, P) == 2
    got = dict(db.execute("SELECT id, skill_categories FROM posting").fetchall())
    assert got == {a: ["L", "O"], b: None, c: None, d: None, e: []}
    assert tc.save(db, P) == 0                         # 바뀐 것이 없으면 쓰지 않는다


def test_column_only_takes_seven_codes(db):
    import psycopg
    pid = add_posting(db, "Z")
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE posting SET skill_categories = ARRAY['Q'] WHERE id = %s", (pid,))


def test_load_team_says_where_the_file_goes(tmp_path):
    """팀원 파일은 로컬 전용이라 없을 수 있다 — Airflow 실패 알림에 어디에 두면 되는지 보이게."""
    with pytest.raises(FileNotFoundError, match="out/team_categories/"):
        tc.load_team(str(tmp_path / "없음.html"))
