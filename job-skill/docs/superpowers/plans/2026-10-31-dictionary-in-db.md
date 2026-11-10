# 표준화 사전을 DB로 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 표준화 사전의 원본을 `capabilities.json`에서 DB로 옮겨, 팀원이 RDS에서 SQL로 고친 사전이 다음 추출부터 쓰이고, 누가 무엇을 바꿨는지 DB에 남게 한다.

**Architecture:** 사전 4개 표(`capability`, `tech`, `tech_capability`, 새 `exclude_word`)가 원본이다. `capdict.py`가 DB에서 사전을 읽어 지금과 같은 모양의 dict로 만들고, `extract_skills.py`는 추출을 시작할 때 한 번 읽어 쓴다. 사전 표에는 트리거를 걸어 `dictionary_change`에 바뀐 줄을 남긴다. 빈 DB는 `db/seed_dictionary.sql`(DB에서 내려받은 SQL)로 채운다.

**Tech Stack:** Python 3.12, psycopg 3, PostgreSQL 17(로컬 Docker `career-db`)·18(RDS), pytest, Airflow 3(태스크는 `pipeline_tasks.py`), Chrome headless(그림 PNG)

**Spec:** `job-skill/docs/superpowers/specs/2026-10-31-dictionary-in-db-design.md`

## Global Constraints

- 작업 폴더 `job-skill/`. Task 1~6은 브랜치 `feature/job-skill`, Task 7에서 `feature/job-skill-aws`로 cherry-pick(지금까지 방식).
- 표는 모두 기본 스키마 `public`. 정해진 값은 **한글 값 + CHECK**, 표·칸마다 한글 `COMMENT`(기존 `db/schema.sql` 방식).
- `db/schema.sql`은 늘 최신 전체 DDL, 이미 있는 DB는 `db/migrations/004_dictionary_in_db.sql`로 바꾼다(여러 번 돌려도 안전).
- 커밋 메시지는 한국말, `Co-Authored-By`·`Generated with` 줄을 넣지 않는다.
- 파일의 줄바꿈(LF/CRLF)은 원래 파일 것을 지킨다.
- 테스트: Docker `career-db`가 켜진 상태에서 `cd job-skill; py -3.12 -m pytest tests -q --ignore=tests/test_dags.py` (DB 테스트는 임시 DB를 만들었다 지움).
- **RDS는 Task 7 전에는 건드리지 않는다.** Airflow는 멈춰 둔 상태(`docker compose -f docker-compose.airflow.yml stop`)로 둔다.
- 기록되는 "바꾼 사람"은 `session_user`(팀원은 접속 뒤 `SET ROLE team`이 되므로 `current_user`가 아님).

## Review Focus

1. 팀원이 어떤 기술이 가리키는 능력을 `is_active = false`로 끔 → 그 연결은 빠지고, 능력이 하나도 안 남은 사용 중 기술은 "확인 필요"로 알린다(추출은 계속). → Task 3 테스트 `test_tech_without_active_capability_is_a_problem`
2. 대소문자·공백만 다른 별칭을 다른 기술에 넣음(`aws`를 `Lambda`의 별칭으로) → 같은 별칭 겹침으로 잡는다. → Task 3 `test_duplicate_alias_ignoring_case_is_a_problem`
3. 한 기술에 대표 능력을 둘 표시 → DB가 막는다. → Task 1 `test_one_primary_per_tech`
4. 값이 그대로인 `UPDATE`(`SET aliases = aliases`) → 기록이 쌓이지 않는다. → Task 1 `test_noop_update_not_logged`
5. 사전이 이미 있는 DB에 시드 SQL을 다시 적용 → 팀원이 지운 항목이 되살아나지 않는다. → Task 2 `test_seed_does_nothing_when_dictionary_exists`

---

### Task 1: DB 구조 — 새 표 2개, 대표 능력 칸, 변경 기록 트리거

**Files:**
- Modify: `db/schema.sql` (③ 표준화 사전 구역)
- Create: `db/migrations/004_dictionary_in_db.sql`
- Test: `tests/test_dictionary_db.py` (새로)

**Interfaces:**
- Produces (DB):
  - `exclude_word(id bigint identity PK, word text NOT NULL, kind text NOT NULL CHECK (kind IN ('LLM 모델','기술 아님','일반 낱말')), UNIQUE(kind, word))`
  - `tech_capability.is_primary boolean NOT NULL DEFAULT false` + 부분 UNIQUE 색인 `tech_capability_one_primary ON tech_capability (tech_id) WHERE is_primary`
  - `dictionary_change(id bigint identity PK, changed_at timestamptz NOT NULL DEFAULT now(), changed_by text NOT NULL, table_name text NOT NULL CHECK (table_name IN ('capability','tech','tech_capability','exclude_word')), action text NOT NULL CHECK (action IN ('넣기','고치기','지우기')), old_row jsonb, new_row jsonb)` + 색인 `(changed_at)`
  - 함수 `log_dictionary_change()` — `SECURITY DEFINER`, `SET search_path = public, pg_catalog`, `changed_by = session_user`, `UPDATE`에서 `to_jsonb(OLD) = to_jsonb(NEW)`면 남기지 않음
  - 트리거 `dictionary_change_log` (AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW) — 4개 표
  - 트리거 `dictionary_no_truncate` (BEFORE TRUNCATE FOR EACH STATEMENT) — 4개 표, 오류 문구: `사전 표는 TRUNCATE 할 수 없습니다(변경 기록이 남지 않음). DELETE 를 쓰세요.`
  - `dictionary_version`: `synced_at` → `first_used_at`(timestamptz NOT NULL DEFAULT now()), COMMENT 표 `'사전 판 (추출에 쓰인 사전 지문과 처음 쓴 시각)'`, `version` `'사전 판 (사전 내용 지문 12자리, 2026-10-31 전에는 0.1.1 같은 번호)'`
  - `extraction_run.dict_version` COMMENT `'사전 판 (사전 내용 지문, 2026-10-31 전 결과는 0.1.1 같은 번호)'`

- [ ] **Step 1: 실패하는 테스트 쓰기** — `tests/test_dictionary_db.py` (`db` 픽스처 = 임시 DB, autocommit)

```python
def test_change_is_logged_with_session_user(db):
    db.execute("INSERT INTO tech (name) VALUES ('시험기술')")
    db.execute("UPDATE tech SET aliases = '{시험}' WHERE name = '시험기술'")
    db.execute("DELETE FROM tech WHERE name = '시험기술'")
    rows = db.execute("""SELECT action, changed_by, old_row->>'name', new_row->'aliases'
                         FROM dictionary_change
                         WHERE table_name = 'tech' AND coalesce(new_row, old_row)->>'name' = '시험기술'
                         ORDER BY id""").fetchall()
    user = db.execute("SELECT session_user").fetchone()[0]
    assert [r[0] for r in rows] == ["넣기", "고치기", "지우기"]
    assert {r[1] for r in rows} == {user}
    assert rows[1][3] == ["시험"] and rows[2][2] == "시험기술"

def test_noop_update_not_logged(db):
    db.execute("INSERT INTO capability (name) VALUES ('시험능력')")
    db.execute("UPDATE capability SET aliases = aliases WHERE name = '시험능력'")
    assert db.execute("""SELECT count(*) FROM dictionary_change
                         WHERE action = '고치기' AND new_row->>'name' = '시험능력'""").fetchone()[0] == 0

def test_truncate_is_blocked(db):
    with pytest.raises(psycopg.errors.RaiseException, match="TRUNCATE"):
        db.execute("TRUNCATE exclude_word")

def test_one_primary_per_tech(db):
    # 기술 하나 + 능력 둘, 둘 다 대표로 표시하면 UniqueViolation
    ...
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute("INSERT INTO tech_capability (tech_id, capability_id, is_primary) VALUES (%s, %s, true)", (t, c2))

def test_exclude_word_kind_is_checked(db):
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("INSERT INTO exclude_word (word, kind) VALUES ('x', '모름')")
```
(Task 2부터 테스트 DB에 시드가 들어와 시드의 기록도 쌓인다. 그래서 위 테스트는 처음부터 '시험기술'·'시험능력' 이름으로만 좁혀 본다. 기술·능력 이름은 시드에 없는 것을 쓴다.)

- [ ] **Step 2: 실패 확인** — `py -3.12 -m pytest tests/test_dictionary_db.py -q` → `relation "dictionary_change" does not exist` 등으로 FAIL

- [ ] **Step 3: `db/schema.sql`에 위 Produces를 넣는다.** 머리말 구역 목록 `③ 표준화 사전`에 `exclude_word`, 새 구역 `④ 사전 변경 기록 dictionary_change`. 머리말의 "원본은 capabilities.json, DB 는 한 방향 복사본" 줄은 "사전의 원본은 DB. 팀원이 SQL 로 고치고, 바뀐 줄은 dictionary_change 에 남는다"로 바꾼다.

- [ ] **Step 4: `004_dictionary_in_db.sql` — 구조 부분** (schema.sql과 같은 DDL을 `IF NOT EXISTS`/`ADD COLUMN IF NOT EXISTS`/`CREATE OR REPLACE FUNCTION`/`DROP TRIGGER IF EXISTS` 뒤 `CREATE TRIGGER`로, `synced_at` 이름 바꾸기는 칸이 있을 때만). 머리말: `-- 2026-10-31 사전의 원본을 DB로(사용자 결정). ... 여러 번 돌려도 안전.`

- [ ] **Step 5: `004` — 이미 사전이 있는 DB용 데이터 부분.** `IF EXISTS (SELECT 1 FROM capability)`일 때만:
  - `exclude_word`가 비어 있으면 `capabilities.json`의 `exclude`(LLM 모델 16, 기술 아님 34, 일반 낱말 11)를 넣는다.
  - `tech_capability`에 `is_primary`가 하나도 없으면, JSON에서 기술마다 **첫 번째 능력**을 대표로 `UPDATE`한다.
  - 두 값 목록은 일회용 스크립트(스크래치 폴더, 커밋하지 않음)로 `capabilities.json`에서 뽑아 `VALUES (...)`로 붙인다.

- [ ] **Step 6: 테스트 통과 확인** — `py -3.12 -m pytest tests/test_dictionary_db.py -q` → PASS, 그리고 전체 `py -3.12 -m pytest tests -q --ignore=tests/test_dags.py` → 기존 것 모두 PASS

- [ ] **Step 7: 커밋** — `feat: 사전 변경 기록(트리거)·스킬이 아닌 낱말 표·기술 대표 능력 칸 — 사전 원본을 DB로 옮기는 준비(004)`

---

### Task 2: 시드 SQL과 `export-dict` — 빈 DB 채우기

**Files:**
- Modify: `db_load.py` (`cmd_init`, 새 `export_dictionary`·`cmd_export_dict`, argparse `export-dict`)
- Create: `db/seed_dictionary.sql` (명령으로 만든 결과물)
- Modify: `tests/conftest.py` (`db_url`: 마이그레이션 뒤 시드 적용)
- Test: `tests/test_dictionary_db.py`

**Interfaces:**
- Consumes: Task 1의 표·칸
- Produces:
  - `db_load.SEED_SQL = os.path.join(HERE, "db", "seed_dictionary.sql")`
  - `db_load.export_dictionary(conn) -> str` — 사전 4개 표를 SQL 글로. 모양: `BEGIN; DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM capability) THEN ... END IF; END $$; COMMIT;` 안에서 `capability`(이름·그룹·별칭·사용 여부, id 순) → `tech`(id 순) → 상위(`parent_id`는 이름으로 찾아 UPDATE) → `tech_capability`(기술·능력 이름으로, `is_primary`) → `exclude_word`(kind, word 순). 사용 안 함(`is_active=false`) 줄도 내보낸다. 같은 사전이면 글자가 똑같이 나온다.
  - `db_load.cmd_export_dict(out: str = SEED_SQL) -> None` — 지금 접속한 DB(aws 브랜치면 RDS)에서 내려받아 파일에 쓰고 `사전 → db/seed_dictionary.sql: 능력 N, 기술 N, 연결 N, 낱말 N` 출력
  - `cmd_init`: `schema.sql` 다음에 `SEED_SQL` 적용
  - conftest `db_url`: `schema.sql` → 마이그레이션 → `SEED_SQL`

- [ ] **Step 1: 실패하는 테스트 쓰기**

```python
def test_seed_fills_empty_db(db):          # conftest 가 시드를 적용한 임시 DB
    assert db.execute("SELECT count(*) FROM capability WHERE name <> '기타'").fetchone()[0] == 61
    assert db.execute("SELECT count(*) FROM tech").fetchone()[0] == 184
    assert db.execute("SELECT count(*) FROM exclude_word").fetchone()[0] == 61
    rds = db.execute("""SELECT c.name FROM tech_capability tc JOIN tech t ON t.id = tc.tech_id
                        JOIN capability c ON c.id = tc.capability_id WHERE t.name = 'RDS' AND tc.is_primary""").fetchone()
    assert rds == ("클라우드",)            # JSON 의 첫 번째 능력이 대표

def test_seed_does_nothing_when_dictionary_exists(db):
    db.execute("DELETE FROM exclude_word WHERE word = 'CTO'")
    db.execute(open(db_load.SEED_SQL, encoding="utf-8").read())
    assert db.execute("SELECT count(*) FROM exclude_word WHERE word = 'CTO'").fetchone()[0] == 0

def test_export_round_trip_is_identical(db):
    assert db_load.export_dictionary(db) == open(db_load.SEED_SQL, encoding="utf-8").read()
```

- [ ] **Step 2: 실패 확인** — 시드 파일이 없어 FAIL
- [ ] **Step 3: `export_dictionary`·`cmd_export_dict`·`cmd_init`·conftest 구현**
- [ ] **Step 4: 첫 시드 만들기 (일회용 절차, 결과 파일만 커밋).** 임시 DB에 `schema.sql` 적용 → 아직 남아 있는 `cmd_sync_dict()`로 `capabilities.json`을 넣음(`DATABASE_URL`을 임시 DB로) → `004` 적용(데이터 부분이 낱말·대표를 채움 — 004의 데이터 부분도 여기서 함께 확인됨) → `export_dictionary`로 `db/seed_dictionary.sql`을 쓴다 → 임시 DB 지움.
- [ ] **Step 5: 통과 확인** — 위 3개 + 전체 테스트 PASS
- [ ] **Step 6: 커밋** — `feat: 사전 내려받기(db_load.py export-dict)와 빈 DB 를 채우는 시드 SQL — 테스트·새 DB 는 시드로 채움`

---

### Task 3: `capdict.py`가 DB에서 사전을 읽기

**Files:**
- Modify: `capdict.py`
- Test: `tests/test_capdict.py` (새로)

**Interfaces:**
- Consumes: Task 1의 표, Task 2의 시드(테스트 DB)
- Produces:
  - `capdict.OTHER = "기타"` (`db_load.OTHER`는 이것을 가져다 쓴다)
  - `load_dictionary(conn) -> dict` — **사용 중(`is_active`)인 줄만**. 모양은 옛 JSON과 같게:
    `{"capabilities": {이름: {"group": str|None, "aliases": [...], "parent": str|None}}, "techs": {이름: {"caps": [대표 먼저, 나머지는 능력ID 순], "aliases": [...], "parent": str|None}}, "exclude": {"llm_models": [...], "not_skill": [...], "generic_words": [...]}, "has_other": bool}`
    - 능력·기술 순서는 id 순. `기타`는 `capabilities`에 넣지 않고 `has_other`로만 알린다(LLM 목록의 `enum`에 `기타`가 두 번 들어가지 않게).
    - 대표가 표시되지 않은 기술은 능력ID가 가장 작은 것이 맨 앞.
    - 사용 안 함 능력을 가리키는 연결, 사용 안 함 상위는 뺀다.
    - `exclude_word.kind` 대응: `LLM 모델`→`llm_models`, `기술 아님`→`not_skill`, `일반 낱말`→`generic_words`
  - `fingerprint(data: dict) -> str` — `json.dumps(data, ensure_ascii=False, sort_keys=True)`의 SHA-256 앞 12자리
  - `check_dictionary(data: dict) -> tuple[list[str], list[str]]` — `(멈출 이유, 확인 필요)`
    - 멈출 이유: 사용 중인 능력 0개 → `'사용 중인 능력이 없음'`, `has_other`가 False → `"'기타' 능력이 없거나 꺼짐"`
    - 확인 필요: 같은 이름·별칭(대소문자·공백 무시)이 서로 다른 두 기술에(또는 두 능력에) 있음, 상위 고리가 제자리로 돌아옴, 능력이 하나도 없는 사용 중 기술
  - `CapDict(data: dict)` — 파일 경로 대신 위 dict를 받는다. `version = fingerprint(data)`. 같은 이름·별칭이 겹치면 **먼저 나온 것(id가 작은 것)**을 쓴다(`setdefault`). 나머지 메서드(`lookup`, `capability`, `satisfies`, `cap_names`)는 그대로.
  - `__main__` 시연은 `db_load.connect()`로 읽어서 돈다.

- [ ] **Step 1: 실패하는 테스트 쓰기** (`db` 픽스처 — 시드가 든 임시 DB)

```python
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

def test_inactive_rows_are_not_used(db):           # 꺼진 기술은 사전에 없음
def test_missing_primary_uses_smallest_capability_id(db):
def test_all_capabilities_off_is_fatal(db):        # WHERE 없이 is_active = false (기타 제외)
def test_other_off_is_fatal(db):
def test_duplicate_alias_ignoring_case_is_a_problem(db):   # Lambda 별칭에 'aws'
def test_parent_cycle_is_a_problem(db):
def test_tech_without_active_capability_is_a_problem(db):
```
(이름만 적은 테스트는 주석의 상황을 만들고 `check_dictionary` 결과 목록에 해당 기술·능력 이름이 든 문장이 있는지 본다.)

- [ ] **Step 2: 일회용 같음 확인** — 커밋 전, `capabilities.json`으로 만든 옛 `CapDict`와 `CapDict(load_dictionary(시드 DB))`의 `capabilities`·`techs`·제외 목록이 같은지(순서 포함, `기타` 제외) 스크립트로 비교해 출력을 남긴다(같아야 함).
- [ ] **Step 3: 구현** → **Step 4: 통과 확인**(새 테스트 + 전체) → **Step 5: 커밋** — `feat: capdict 가 DB 사전을 읽음 — 사용 중인 줄만, 사전 지문, 망가진 사전·어긋난 항목 검사`

---

### Task 4: 추출이 DB 사전을 쓰고, 문제를 Slack 으로 알리기

**Files:**
- Modify: `extract_skills.py` (`CD` 전역, `REQ` enum, `main`, 새 `use_dictionary`·`prepare_dictionary`·`DictionaryBroken`, `extract_one`의 `dict_version`, 머리말)
- Modify: `pipeline_tasks.py` (`step_extract`)
- Modify: `notify.py` (새 `msg_dictionary`)
- Modify: `tests/conftest.py` (사전 픽스처), `tests/test_run_model.py`, `tests/test_extract_budget.py`, `tests/test_prompt_rules.py`, `tests/test_pipeline_tasks.py`

**Interfaces:**
- Consumes: Task 3의 `CapDict`, `load_dictionary`, `check_dictionary`
- Produces:
  - `extract_skills.CD: CapDict | None = None` (import 할 때 사전을 읽지 않는다)
  - `extract_skills.use_dictionary(cd: CapDict) -> None` — `CD`를 바꾸고 `REQ["properties"]["capability"]["enum"]`을 `cd.cap_names() + ["기타"]`로 제자리에서 바꾼다(`SCHEMA`가 같은 dict를 가리킴)
  - `class DictionaryBroken(Exception)` — `DictionaryBroken(reasons: list[str])`, `.reasons`에 멈출 이유 목록, 메시지는 `"; ".join(reasons)`
  - `extract_skills.prepare_dictionary(conn) -> tuple[CapDict, list[str]]` — 읽고 검사. 멈출 이유가 있으면 `DictionaryBroken(이유)`, 아니면 `use_dictionary`를 부르고 `(CapDict, 확인 필요 목록)`을 돌려준다
  - `main`: 입력이 0건이면 지금처럼 DB 없이 끝(테스트 `test_main_with_zero_inputs_exits_cleanly` 유지). 있으면 `import db_load`(함수 안 — 순환 import 피함) 후 `prepare_dictionary`. 결과를 `EX/_dictionary.json`에 `{"version": ..., "fatal": [...], "problems": [...]}`로 쓴다. 멈출 이유가 있으면 이 파일을 쓴 뒤 `sys.exit("사전이 망가져 추출을 멈춥니다: ...")`.
  - `extract_one` 결과의 `dict_version = CD.version` (지문 12자리)
  - `notify.msg_dictionary(dag_label: str, problems: list[str]) -> str` → `⚠️ {dag_label} · 사전 확인 필요 {n}건 (추출은 계속함)` + 줄마다 `- 문제`
  - `step_extract`: 지난 `_dictionary.json`도 시작 때 지운다. `run_script`가 `CalledProcessError`로 끝나고 `_dictionary.json`의 `fatal`이 있으면 `RuntimeError(f"사전이 망가져 추출을 멈춤: {...}")`로 바꿔 던진다(Airflow 실패 알림에 이유가 보이게). 정상 끝이면 `problems`가 있을 때 `notify.send(notify.msg_dictionary(...))`.
  - conftest: 세션 픽스처 `seed_dictionary` — 시드를 적용한 임시 DB 하나에서 `CapDict(load_dictionary(conn))`를 만들고 DB는 지운다. 함수 픽스처 `use_seed_dictionary`(extract_skills에 `use_dictionary`). `extract_skills`를 쓰는 테스트 모듈은 `pytestmark = pytest.mark.usefixtures("use_seed_dictionary")`.

- [ ] **Step 1: 실패하는 테스트 쓰기**

```python
# test_run_model.py — 바꾸기
assert len(r["prompt_version"]) == 12 and len(r["dict_version"]) == 12 and len(r["input_hash"]) == 64

# test_dictionary_db.py (또는 새 test_extract_dictionary.py)
def test_prepare_dictionary_stops_on_broken_dictionary(db):
    db.execute("UPDATE capability SET is_active = false WHERE name = '기타'")
    with pytest.raises(ex.DictionaryBroken, match="기타"):
        ex.prepare_dictionary(db)

def test_teammate_alias_is_used_in_next_extraction(db):
    assert ex.prepare_dictionary(db)[0].lookup("스프링부트3")["kind"] == "unknown"     # 고치기 전
    db.execute("UPDATE tech SET aliases = aliases || '{스프링부트3}' WHERE name = 'Spring Boot'")
    cd, problems = ex.prepare_dictionary(db)
    assert cd.lookup("스프링부트3")["name"] == "Spring Boot" and problems == []

def test_enum_follows_dictionary(db):
    db.execute("INSERT INTO capability (name) VALUES ('시험능력')")
    ex.prepare_dictionary(db)
    assert "시험능력" in ex.REQ["properties"]["capability"]["enum"]
    assert ex.REQ["properties"]["capability"]["enum"].count("기타") == 1

# test_pipeline_tasks.py
def test_dictionary_problems_are_sent_to_slack(...):   # run_script 를 가짜로: _dictionary.json 에 problems 2개 → notify.send 문구에 '사전 확인 필요 2건'
def test_broken_dictionary_fails_task_with_reason(...): # run_script 가 CalledProcessError + fatal → RuntimeError('사전이 망가져 ...')
```
- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4: 통과 확인**(전체) → **Step 5: 커밋** — `feat: 추출이 DB 사전을 씀 — 팀원이 고친 사전이 다음 추출부터 반영, 망가진 사전은 멈추고 어긋난 항목은 Slack 으로`

---

### Task 5: 파일 사전 지우기와 남은 연결 정리

**Files:**
- Delete: `capabilities.json`
- Modify: `db_load.py` (`DICT_JSON`·`cmd_sync_dict`·argparse `sync-dict` 삭제, 머리말 사용법, `insert_run`이 `dictionary_version`에 판 기록)
- Modify: `README.md`(로컬 브랜치 부분), `extract_skills.py`·`capdict.py` 머리말, 그 밖에 `capabilities.json`을 가리키는 설명
- Test: `tests/test_db_queries.py` 또는 `tests/test_dictionary_db.py`

**Interfaces:**
- Consumes: Task 2의 `export-dict`, Task 4의 `dict_version`
- Produces: `insert_run`이 새 실행을 넣을 때 `INSERT INTO dictionary_version (version) VALUES (dict_version) ON CONFLICT DO NOTHING`

- [ ] **Step 1: 실패하는 테스트** — `insert_run`으로 실행 하나를 넣으면 `dictionary_version`에 그 `dict_version` 줄이 생기고, 같은 판으로 또 넣어도 줄은 하나.
- [ ] **Step 2: 구현·삭제** — README: 파일 표(46행)는 `capdict.py`(DB 사전 조회)로, 처리 순서 4번(23행)은 "DB의 표준화 사전으로", 실행 예(80행)의 `sync-dict`는 지우고 "사전은 DB가 원본 — 바꾼 뒤 `py -3.12 db_load.py export-dict`로 내려받아 커밋(빈 DB·테스트용)" 한 줄. `db_load.py` 표(48행) 설명도 맞춘다.
- [ ] **Step 3: 확인** — `git grep -n "capabilities.json" -- . ':!docs/superpowers'` 결과 없음, `git grep -n "sync-dict\|sync_dict" -- . ':!docs/superpowers'` 결과 없음, 전체 테스트 PASS
- [ ] **Step 4: 로컬 DB 적용** — README의 "번호 순서대로 적용" 명령으로 로컬 `career-db`에 `004` 적용 후 `py -3.12 db_load.py export-dict --out <스크래치>/local.sql`이 시드와 같은지 비교(다르면 로컬 사전이 옛 판이었다는 뜻 — 차이를 보고만 하고 시드는 그대로)
- [ ] **Step 5: 커밋** — `refactor: 사전 파일(capabilities.json)과 sync-dict 빼기 — 사전 원본은 DB, 추출에 쓴 판은 dictionary_version 에 기록`

---

### Task 6: ERD 그림 2개와 물리 설계 문서

**Files:**
- Modify: `docs/erd.svg`, `docs/erd.png`, `docs/erd-physical.svg`, `docs/erd-physical.png`, `docs/physical-design.md`

- [ ] **Step 1: 그림 고치기** — 두 그림의 ③ 표준화 사전 구역에 `exclude_word`(스킬이 아닌 낱말), `tech_capability.is_primary`(대표 능력), `dictionary_version.first_used_at`, 새 구역 `dictionary_change`(사전 변경 기록 — 사전 4개 표에서 트리거로 기록, 선은 점선 + "트리거" 글자)를 기존 그림 방식(상자·글꼴·색)대로 넣는다. 필요하면 캔버스(`width`·`height`·`viewBox`)를 키운다.
- [ ] **Step 2: PNG 다시 만들기** — svg 크기 W×H 그대로, 2배:
  `"C:/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --window-size=W,H --default-background-color=ffffffff --screenshot=<스크래치>/x.png "file:///C:/makingprogram/캡스톤1/job-skill/docs/<이름>.svg"` → 눈으로 확인(잘린 곳·겹친 글자 없음) 뒤 `docs/`로 복사
- [ ] **Step 3: `physical-design.md`** — 새 표 2개 칸 표(한글·영어·자료형·제약), `tech_capability`에 대표 능력 줄, `dictionary_version` 뜻 바뀜, 변경 기록 트리거·TRUNCATE 막음 설명, 맨 위 "바꿈" 목록에 `2026-10-31 바꿈(사용자 결정): 사전의 원본을 DB로 ...` 한 줄, 팀원이 사전을 고치는 SQL 예 3개(별칭 더하기, 기술 넣고 능력 잇기 + 대표 표시, 끄기)와 기록 보기 SQL 1개
- [ ] **Step 4: 커밋** — `docs: ERD·물리 설계에 사전 변경 기록·스킬이 아닌 낱말 표·대표 능력 칸`

---

### Task 7: aws 브랜치와 RDS 적용

**Files:**
- `feature/job-skill-aws`: cherry-pick, `README.md`의 AWS 부분
- RDS(마스터 `career`로)

- [ ] **Step 1: cherry-pick** — Task 1~6 커밋을 순서대로. 충돌이 나면 aws 쪽 RDS 코드(`database_url`)를 지킨다.
- [ ] **Step 2: AWS README** — 준비 3단계의 `sync-dict` 줄 삭제(`init`이 시드로 채움). "12/20까지 쓰고 나면 … RDS를 지운다" 줄 앞에 **"RDS를 지우기 전에 `py -3.12 db_load.py export-dict`로 사전을 내려받아 커밋한다(팀이 다듬은 사전이 사라지지 않게)"**. 팀원용 한 단락: 사전 4개 표는 SQL로 직접 고친다, 고친 것은 다음 추출부터, 기록은 `dictionary_change`, 예시는 `docs/physical-design.md`.
- [ ] **Step 3: aws 브랜치 전체 테스트 PASS**(로컬 DB를 씀) → 커밋 `docs(aws): 사전은 RDS 가 원본 — 지우기 전 export-dict, 팀원이 사전 고치는 법`
- [ ] **Step 4: RDS 적용** — 다른 접속이 없는지 확인 → `004` 적용 → 권한:
  `GRANT SELECT, INSERT, UPDATE, DELETE ON exclude_word TO team`, `GRANT SELECT ON dictionary_change TO team`, `REVOKE INSERT, UPDATE, DELETE ON dictionary_version FROM team`(이제 추출 기록이라 읽기만)
- [ ] **Step 5: RDS 확인** — `export-dict --out <스크래치>/rds.sql`이 `db/seed_dictionary.sql`과 같음(다르면 팀원이 이미 고친 것 — 사용자에게 보여 주고 RDS 쪽을 커밋할지 묻는다). `dongmin`으로 별칭 하나 고침 → `dictionary_change`에 `changed_by = 'dongmin'` 줄 확인 → 되돌림(되돌린 것도 기록됨을 확인). `dongmin`으로 `dictionary_change` 지우기·`TRUNCATE tech` 시도 → 막힘.
- [ ] **Step 6: 사용자에게 알림** — Airflow는 멈춘 상태, 다시 켜는 명령(`docker compose -f docker-compose.airflow.yml up -d`), push는 하지 않았음.
