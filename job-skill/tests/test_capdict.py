"""capdict — DB(시드를 넣은 임시 DB)에서 사전 읽기, 사전 지문, 망가진 사전·어긋난 항목 검사."""
from __future__ import annotations

from capdict import CapDict, check_dictionary, fingerprint, load_dictionary


def test_seed_behaves_like_old_json(db):
    cd = CapDict(load_dictionary(db))
    assert cd.lookup("K8s")["name"] == "Kubernetes"
    assert cd.lookup("EC2")["parent"] == "AWS"
    assert cd.lookup("Claude Code")["kind"] == "exclude"
    assert cd.lookup("RDS")["caps"][0] == "클라우드"
    assert "기타" not in cd.cap_names() and len(cd.cap_names()) == 61
    assert check_dictionary(load_dictionary(db)) == ([], [])


def test_fingerprint_changes_when_dictionary_changes(db):
    before = fingerprint(load_dictionary(db))
    assert before == fingerprint(load_dictionary(db)) and len(before) == 12
    db.execute("UPDATE tech SET aliases = aliases || '{스프링부트3}' WHERE name = 'Spring Boot'")
    assert fingerprint(load_dictionary(db)) != before
    assert CapDict(load_dictionary(db)).version == fingerprint(load_dictionary(db))


def test_inactive_rows_are_not_used(db):
    db.execute("UPDATE tech SET is_active = false WHERE name = 'Kubernetes'")
    assert CapDict(load_dictionary(db)).lookup("K8s")["kind"] == "unknown"


def test_missing_primary_uses_smallest_capability_id(db):
    db.execute("UPDATE tech_capability SET is_primary = false WHERE tech_id = (SELECT id FROM tech WHERE name = 'RDS')")
    smallest = db.execute("""SELECT c.name FROM tech_capability tc JOIN capability c ON c.id = tc.capability_id
                             WHERE tc.tech_id = (SELECT id FROM tech WHERE name = 'RDS') ORDER BY c.id LIMIT 1""").fetchone()[0]
    assert load_dictionary(db)["techs"]["RDS"]["caps"][0] == smallest


def test_all_capabilities_off_is_fatal(db):
    db.execute("UPDATE capability SET is_active = false WHERE name <> '기타'")
    fatal, _ = check_dictionary(load_dictionary(db))
    assert "사용 중인 능력이 없음" in fatal


def test_other_off_is_fatal(db):
    db.execute("UPDATE capability SET is_active = false WHERE name = '기타'")
    fatal, _ = check_dictionary(load_dictionary(db))
    assert any("'기타'" in f for f in fatal)


def test_duplicate_alias_ignoring_case_is_a_problem(db):
    db.execute("UPDATE tech SET aliases = aliases || '{aws}' WHERE name = 'Lambda'")
    fatal, problems = check_dictionary(load_dictionary(db))
    assert fatal == [] and any("AWS" in p and "Lambda" in p for p in problems)
    assert CapDict(load_dictionary(db)).lookup("aws")["name"] == "AWS"     # 겹치면 먼저 나온 것(id 가 작은 것)


def test_parent_cycle_is_a_problem(db):
    db.execute("UPDATE tech SET parent_id = (SELECT id FROM tech WHERE name = 'EC2') WHERE name = 'AWS'")
    _, problems = check_dictionary(load_dictionary(db))
    assert any("상위" in p and "AWS" in p and "EC2" in p for p in problems)


def test_tech_without_active_capability_is_a_problem(db):
    db.execute("UPDATE capability SET is_active = false WHERE name = '컨테이너 오케스트레이션'")
    fatal, problems = check_dictionary(load_dictionary(db))
    assert fatal == [] and any("Kubernetes" in p for p in problems)


# ---------------------------------------------------------------- 최종 검토에서 찾은 것

def test_capability_parent_cycle_does_not_hang(db):
    """능력 상위가 고리(데이터베이스 → 관계형 DB → 데이터베이스)여도 충족 판정이 끝난다(매일 수집이 멈추면 안 됨)."""
    import threading
    db.execute("UPDATE capability SET parent_id = (SELECT id FROM capability WHERE name = '관계형 DB') WHERE name = '데이터베이스'")
    cd = CapDict(load_dictionary(db))
    out = []
    t = threading.Thread(target=lambda: out.append(cd.satisfies(["관계형 DB"], "백엔드 프레임워크")), daemon=True)
    t.start()
    t.join(timeout=3)
    assert not t.is_alive() and out == [False]
    assert cd.satisfies(["관계형 DB"], "데이터베이스")


def test_all_techs_off_is_fatal(db):
    db.execute("UPDATE tech SET is_active = false")
    fatal, _ = check_dictionary(load_dictionary(db))
    assert "사용 중인 기술이 없음" in fatal


def test_no_tech_capability_links_is_fatal(db):
    db.execute("DELETE FROM tech_capability")
    fatal, _ = check_dictionary(load_dictionary(db))
    assert "기술과 능력을 잇는 연결이 없음" in fatal


def test_empty_llm_word_does_not_exclude_everything(db):
    data = load_dictionary(db)
    data["exclude"]["llm_models"] += ["", "  "]
    assert CapDict(data).lookup("MySQL")["kind"] == "tech"


# ---------------------------------------------------------------- 작은 문제(사용자와 하나씩 정함, 2026-11-01)

def test_dictionary_is_read_as_one_snapshot(db_url):
    """추출을 시작한 순간의 모습으로 한 번에 읽는다 — 읽는 사이 팀원이 커밋한 것은 다음 추출부터."""
    import psycopg

    with psycopg.connect(db_url) as reader, psycopg.connect(db_url, autocommit=True) as writer:
        class Reader:   # 첫 SELECT(능력 읽기) 바로 뒤에 팀원이 기술을 넣고 커밋한다
            info, done = reader.info, False

            def transaction(self):
                return reader.transaction()

            def execute(self, query, *a, **k):
                r = reader.execute(query, *a, **k)
                if not self.done and str(query).lstrip().upper().startswith("SELECT"):
                    self.done = True
                    writer.execute("INSERT INTO tech (name) VALUES ('시험기술')")
                return r

        assert "시험기술" not in load_dictionary(Reader())["techs"]
        assert "시험기술" in load_dictionary(reader)["techs"]   # 다음에 읽으면 보임


def test_llm_word_does_not_hide_exact_tech(db):
    """사전에 있는 이름과 정확히 같으면 기술 — 'llama'(LLM 모델) 때문에 LlamaIndex 가 빠지지 않는다."""
    cd = CapDict(load_dictionary(db))
    assert cd.lookup("LlamaIndex")["kind"] == "tech"
    assert cd.lookup("Llama 3")["kind"] == "exclude"
