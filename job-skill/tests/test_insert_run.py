"""db_load.insert_run — 추출 결과(자리·한 줄·요건·요건 기술)를 DB 에 넣기, 다시 추출하면 '현재 사용'은 새 결과 하나.
웹이 읽는 표라 칸이 맞게 들어가는지 본다. 지어낸 결과, 시드 사전이 든 임시 DB."""
from __future__ import annotations

from test_db_queries import add_posting


def req(cap, techs=(), relation="예시"):
    return {"capability": cap, "cap_ok": True, "relation": relation, "techs": list(techs)}


def tech(name, kind="tech"):
    return {"raw": name, "name": name, "kind": kind}


def item(text, *reqs):
    return {"text": text, "quote": text, "reqs": list(reqs)}


RESULT = {"model": "gpt-5.6-luna", "prompt_version": "p" * 12, "dict_version": "d" * 12, "input_hash": "1" * 64,
          "input_tokens": 10, "output_tokens": 5,
          "positions": [
              {"name": "백엔드 개발자", "it_job": True, "career": "경력", "years": "3~5년",
               "required": [item("Java·FooDB 경험", req("프로그래밍 언어", [tech("Java"), tech("FooDB", "unknown")]))],
               "preferred": [item("사내 솔루션 경험", req("기타:사내 솔루션", relation="능력만"))],
               "duties": [item("서비스 설계", req("없는 능력 이름", relation="능력만"))], "other": []},
              {"name": "영업 담당", "it_job": False, "career": "신입", "years": "",
               "required": [item("운전면허", req("기타:운전면허", relation="능력만"))], "preferred": [], "duties": [], "other": []}]}


def _insert(db, tmp_path, posting_id, r):
    import db_load
    path = tmp_path / "A.json"
    path.write_text("{}", encoding="utf-8")
    cap_id = dict(db.execute("SELECT name, id FROM capability").fetchall())
    tech_id = dict(db.execute("SELECT name, id FROM tech").fetchall())
    return db_load.insert_run(db, posting_id, r, None, str(path), cap_id, tech_id)


def test_positions_items_requirements_are_saved(db, tmp_path):
    n = _insert(db, tmp_path, add_posting(db, "A"), RESULT)
    assert n == {"자리": 2, "한 줄": 3, "요건": 3, "요건 기술": 2}
    assert db.execute("SELECT name, is_it, min_years, max_years FROM recruit_unit ORDER BY seq").fetchall() == [
        ("백엔드 개발자", True, 3, 5), ("영업 담당", False, None, None)]
    assert db.execute("""SELECT u.name, i.category FROM unit_item i JOIN recruit_unit u ON u.id = i.unit_id
                         ORDER BY i.id""").fetchall() == [("백엔드 개발자", "필수"), ("백엔드 개발자", "우대"), ("백엔드 개발자", "업무")]   # 비IT 자리는 항목 없음
    assert db.execute("""SELECT c.name, r.other_name, r.relation FROM requirement r JOIN capability c ON c.id = r.capability_id
                         ORDER BY r.id""").fetchall() == [
        ("프로그래밍 언어", "", "예시"), ("기타", "사내 솔루션", "능력만"), ("기타", "없는 능력 이름", "능력만")]   # 사전 밖 능력은 기타 + 이름
    assert db.execute("""SELECT rt.written_name, t.name FROM requirement_tech rt LEFT JOIN tech t ON t.id = rt.tech_id
                         ORDER BY rt.id""").fetchall() == [("Java", "Java"), ("FooDB", None)]   # 사전에 없는 기술은 기술ID 비움


def test_reextraction_keeps_one_current_run(db, tmp_path):
    """같은 공고를 다시 추출하면 옛 결과는 '현재 아님'(false), 새 결과만 '현재 사용'(true). 같은 결과를 또 넣으면 건너뛴다."""
    pid = add_posting(db, "A")
    assert _insert(db, tmp_path, pid, RESULT) is not None
    assert _insert(db, tmp_path, pid, {**RESULT, "input_hash": "2" * 64}) is not None
    assert _insert(db, tmp_path, pid, {**RESULT, "input_hash": "2" * 64}) is None
    assert db.execute("SELECT input_hash, is_current FROM extraction_run ORDER BY id").fetchall() == [
        ("1" * 64, False), ("2" * 64, True)]
