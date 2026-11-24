# 사람 검토(정상·제외·다시) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `extraction_run.review_result` 를 정상·제외·다시로 바꾸고 피드백 칸을 더해, '다시'는 다음 ① 때 피드백을 붙여 다시 추출하고 '제외'는 자동 처리에서 뺀다.

**Architecture:** DB 는 마이그레이션 010 하나(칸·제약·팀원 칸 권한). DAG 는 기존 '밀린 공고' 흐름에 '현재 결과가 다시인 공고'를 더하고, 피드백은 실행 폴더의 `feedback.json` → `posting_inputs` → `llm_input` 으로 간다. '제외'는 `open_postings` 에서 빠져 변경·마감 확인을 하지 않는다.

**Tech Stack:** Python 3.12, psycopg 3, PostgreSQL 16(RDS), pytest(로컬 Docker career-db / CI 임시 PostgreSQL)

**Spec:** `job-skill/docs/superpowers/specs/2026-11-24-review-decision-design.md`

## Global Constraints

- 검토 결과 값은 정확히 `정상`, `제외`, `다시` 세 개. 비어 있으면 아직 안 봄.
- '다시'이면 `review_feedback` 이 빈칸만이 아닌 글이어야 한다. 검토 결과와 검토 시각은 둘 다 있거나 둘 다 없다(기존 제약 `extraction_run_check` 그대로).
- 팀원 역할 `team` 에는 `extraction_run` 의 `review_result`, `review_feedback`, `reviewed_at` 세 칸만 UPDATE 를 더한다. 다른 권한은 바꾸지 않는다. `team` 역할이 없는 DB(로컬·CI)에서도 마이그레이션이 실패하면 안 된다.
- 마이그레이션은 여러 번 돌려도 같은 결과. 시험 DB 는 `schema.sql` 을 만든 뒤 모든 마이그레이션을 다시 돌리므로 새 구조 위에서도 돌아야 한다.
- 피드백이 없으면 LLM 입력은 지금과 글자 하나 다르지 않아야 한다(입력 지문이 바뀌면 같은 공고가 새 결과로 또 들어감).
- 커밋 메시지는 한국어, Claude 표시 줄(Co-Authored-By·Generated with)을 넣지 않는다. 작업 브랜치 `feature/requirement-embedding`. 이 폴더에서 브랜치를 바꾸지 않는다(노트북 Airflow 가 씀).
- 시험 실행: `cd job-skill && PYTHONIOENCODING=utf-8 py -3.12 -m pytest tests/<파일> -q` (DB 시험은 Docker career-db 가 켜져 있어야 돈다. 꺼져 있으면 건너뜀 — 그때는 CI 결과로 확인).

## Review Focus

- '다시'에 빈칸·공백만 있는 피드백 → DB 가 막아야 한다 (Task 1 `test_review_values_and_feedback_rule`).
- 같은 피드백으로 두 번 '다시' → 두 번째 재추출도 새 결과로 저장돼야 한다(안 그러면 매일 추출만 하고 저장 안 됨) (Task 4 `test_load_saves_rerun_after_sent_back`).
- 마감된 공고에 '다시' → 다시 추출하지 않는다 (Task 2 `test_pending_includes_sent_back_with_feedback`).
- ③ 일회성 수집처럼 `feedback.json` 이 없는 실행 → 피드백 없이 평소처럼 (Task 3 `test_posting_inputs_reads_feedback`).
- '제외'한 공고가 사람인에서 수정·마감됨 → 변경·마감 확인 대상에 들어오지 않는다 (Task 2 `test_open_postings_skips_excluded`).

---

### Task 1: DB — 마이그레이션 010 과 schema.sql

**Files:**
- Create: `job-skill/db/migrations/010_review_decision.sql`
- Modify: `job-skill/db/schema.sql` (extraction_run 정의·주석, 끝에 팀원 권한 블록)
- Test: `job-skill/tests/test_review_decision.py` (새 파일)

**Interfaces:**
- Produces: 칸 `extraction_run.review_feedback text`, 제약 `extraction_run_review_result_check`(정상·제외·다시), `extraction_run_review_feedback_check`. 시험 도우미는 `tests/test_db_queries.py` 의 `add_posting(conn, no, status=, deadline=)`, `add_run(conn, posting_id, current=)` 를 가져다 쓴다.

- [ ] **Step 1: 실패하는 시험 쓰기** — `tests/test_review_decision.py`

```python
from test_db_queries import add_posting, add_run

def review(conn, run_id, result, feedback=None):
    conn.execute("UPDATE extraction_run SET review_result=%s, review_feedback=%s, reviewed_at=now() WHERE id=%s",
                 (result, feedback, run_id))

def test_review_values_and_feedback_rule(db):
    run = add_run(db, add_posting(db, "1"))
    for result, fb in (("다시", None), ("다시", "  "), ("문제없음", None)):
        with pytest.raises(psycopg.errors.CheckViolation):
            review(db, run, result, fb)
    with pytest.raises(psycopg.errors.CheckViolation):          # 결과만 있고 시각 없음
        db.execute("UPDATE extraction_run SET review_result='정상' WHERE id=%s", (run,))
    for result, fb in (("정상", None), ("제외", None), ("다시", "자리를 하나로")):
        review(db, run, result, fb)

def test_migration_010_converts_old_db_and_is_repeatable(db):
    # 옛 구조 흉내: 피드백 칸 없음 + 옛 값(문제없음/고침) 제약, 옛 값이 든 줄 하나
    db.execute("ALTER TABLE extraction_run DROP COLUMN review_feedback, DROP CONSTRAINT extraction_run_review_result_check")
    db.execute("ALTER TABLE extraction_run ADD CONSTRAINT extraction_run_review_result_check CHECK (review_result IN ('문제없음','고침'))")
    run = add_run(db, add_posting(db, "1"))
    db.execute("UPDATE extraction_run SET review_result='고침', reviewed_at=now() WHERE id=%s", (run,))
    sql = open(MIGRATION_010, encoding="utf-8").read()
    db.execute(sql); db.execute(sql)
    assert db.execute("SELECT review_result FROM extraction_run WHERE id=%s", (run,)).fetchone()[0] == "정상"
    review(db, run, "다시", "피드백")                               # 새 칸·새 값이 된다

def test_team_can_write_only_review_columns(db):
    db.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='team') THEN CREATE ROLE team NOLOGIN; END IF; END $$")
    db.execute("GRANT SELECT ON extraction_run TO team")             # RDS 와 같은 읽기 권한
    db.execute(open(MIGRATION_010, encoding="utf-8").read())
    run = add_run(db, add_posting(db, "1"))
    db.execute("SET ROLE team")
    try:
        review(db, run, "다시", "자리를 하나로")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute("UPDATE extraction_run SET is_current=false WHERE id=%s", (run,))
    finally:
        db.execute("RESET ROLE")
```

(`MIGRATION_010` = `os.path.join(HERE, "db", "migrations", "010_review_decision.sql")`, `HERE` 는 `from conftest import HERE`(job-skill/). 시험 DB 는 시험마다 지워지지만 역할 `team` 은 클러스터 전체라 남는다 — 그대로 둔다.)

- [ ] **Step 2: 실패 확인** — `pytest tests/test_review_decision.py -q` → FAIL(`review_feedback` 칸 없음 / 파일 없음)

- [ ] **Step 3: `010_review_decision.sql` 쓰기** — 007·008 과 같은 머리(날짜·사용자 결정·"여러 번 돌려도 안전"), `BEGIN; SET LOCAL search_path TO public; … COMMIT;`. 순서:
  1. `ADD COLUMN IF NOT EXISTS review_feedback text`
  2. 두 제약 `DROP CONSTRAINT IF EXISTS`(`extraction_run_review_result_check`, `extraction_run_review_feedback_check`)
  3. `UPDATE extraction_run SET review_result = '정상' WHERE review_result IN ('문제없음', '고침')`
  4. `ADD CONSTRAINT extraction_run_review_result_check CHECK (review_result IN ('정상', '제외', '다시'))`, `ADD CONSTRAINT extraction_run_review_feedback_check CHECK (review_result IS DISTINCT FROM '다시' OR btrim(coalesce(review_feedback, '')) <> '')`
  5. 칸 주석: `review_result` = `'검토 결과 (정상: 결과 맞음 / 제외: 앞으로 자동 처리·웹에서 뺌 / 다시: 피드백을 붙여 다음 ① 때 다시 추출, 안 봤으면 비움)'`, `review_feedback` = `'검토 피드백 (다시일 때 꼭, 다시 추출할 때 LLM 입력 끝에 붙인다)'`
  6. `DO $$ … IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'team') THEN GRANT UPDATE (review_result, review_feedback, reviewed_at) ON extraction_run TO team; END IF … $$;`

- [ ] **Step 4: `schema.sql` 를 같은 모양으로** — `review_result` 줄의 CHECK 를 이름 붙인 세 값 제약으로, `review_feedback text` 칸과 피드백 제약 추가, 두 칸 주석을 Step 3 문구로, 파일 끝 `COMMIT` 앞에 Step 3-6 의 권한 블록.

- [ ] **Step 5: 통과 확인** — `pytest tests/test_review_decision.py tests/test_migrate.py tests/test_db_queries.py -q` → PASS

- [ ] **Step 6: 커밋** — `feat(db): 검토 결과를 정상·제외·다시로 + 피드백 칸, 팀원은 검토 칸 3개만 쓰기(010)`

### Task 2: 밀린 공고에 '다시', 확인 대상에서 '제외' 빼기

**Files:**
- Modify: `job-skill/db_queries.py` (`pending_postings`, `open_postings`, 머리 설명의 '밀린 공고' 정의)
- Test: `job-skill/tests/test_review_decision.py`

**Interfaces:**
- Consumes: Task 1 의 칸·값.
- Produces: `pending_postings(conn) -> list[dict]` 각 줄에 `feedback: str` 칸(다시면 피드백, 아니면 `''`). `open_postings(conn)` 는 현재 결과가 `제외`인 공고를 뺀다.

- [ ] **Step 1: 실패하는 시험 쓰기**

```python
def test_pending_includes_sent_back_with_feedback(db):
    import db_queries as q
    add_posting(db, "1")                                                        # 실행 없음 → 밀린 공고, 피드백 ''
    review(db, add_run(db, add_posting(db, "2")), "다시", "공통지원요건은 자리가 아님")
    review(db, add_run(db, add_posting(db, "3")), "정상")
    review(db, add_run(db, add_posting(db, "4")), "제외")
    p5 = add_posting(db, "5")
    review(db, add_run(db, p5, current=False), "다시", "옛 피드백")               # 다시 뽑은 결과가 현재 → 아님
    add_run(db, p5)
    review(db, add_run(db, add_posting(db, "6", status="마감")), "다시", "마감됨")  # 마감 → 아님
    rows = q.pending_postings(db)
    assert [(r["rec_idx"], r["feedback"]) for r in rows] == [("1", ""), ("2", "공통지원요건은 자리가 아님")]
    assert rows[1]["role"] == "백엔드" and rows[1]["career"] == "신입 · 경력"      # 공고 정보는 DB 에서(지워지지 않음)

def test_open_postings_skips_excluded(db):
    import db_queries as q
    review(db, add_run(db, add_posting(db, "A")), "제외")
    review(db, add_run(db, add_posting(db, "B")), "정상")
    add_posting(db, "C")
    assert [r["rec_idx"] for r in q.open_postings(db)] == ["B", "C"]
    assert "A" in q.known_posting_nos(db)                                        # 새 공고로 다시 잡히지 않음
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_review_decision.py -q` → FAIL(`feedback` 키 없음, A 가 나옴)

- [ ] **Step 3: 고치기**
  - `pending_postings`: 현재 실행을 `LEFT JOIN extraction_run e ON e.posting_id = p.id AND e.is_current`, 조건 `NOT EXISTS(실행 하나도 없음) OR e.review_result = '다시'`, 칸 `CASE WHEN e.review_result = '다시' THEN e.review_feedback ELSE '' END AS feedback`. 진행 공고 조건(`OPEN`)·정렬은 그대로.
  - `open_postings`: `AND NOT EXISTS (SELECT 1 FROM extraction_run e WHERE e.posting_id = p.id AND e.is_current AND e.review_result = '제외')`.
  - 모듈 설명의 '밀린 공고' 줄과 두 함수 설명을 새 규칙으로.

- [ ] **Step 4: 통과 확인** — `pytest tests/test_review_decision.py tests/test_db_queries.py tests/test_recheck.py -q` → PASS

- [ ] **Step 5: 커밋** — `feat: 검토 '다시'는 밀린 공고로(피드백 함께), '제외'는 변경·마감 확인에서 뺌`

### Task 3: 피드백을 LLM 입력까지

**Files:**
- Modify: `job-skill/pipeline_tasks.py` (`step_collect`, `daily_report` 수집 줄)
- Modify: `job-skill/extract_skills.py` (`FEEDBACK` 상수, `posting_inputs`, `llm_input`)
- Test: `job-skill/tests/test_pipeline_tasks.py`, `job-skill/tests/test_run_model.py`

**Interfaces:**
- Consumes: Task 2 의 `pending_postings` 줄 `feedback`.
- Produces: 실행 폴더 `feedback.json` = `{공고번호: 피드백}`(피드백 있는 것만). `step_collect` 결과에 `"다시": int`. `extract_skills.FEEDBACK = os.path.join(DATA, "feedback.json")`(`common.DATA`). `posting_inputs()` 각 값에 `feedback: str`. `llm_input(inp, extra="")` 는 `inp.get("feedback")` 이 있으면 공고 글 뒤, `[다시 확인]` 앞에 다음을 붙인다:
  `"\n\n[검토 피드백] 사람이 앞선 정리를 보고 남긴 말이다. 반영해서 정리하라.\n" + feedback`

- [ ] **Step 1: 실패하는 시험 쓰기**
  - `test_pipeline_tasks.py::test_daily_collect_writes_feedback` — 보류 stash 의 같은 이름 시험 그대로(P1 피드백에 줄바꿈 포함, P2 는 ''): `feedback.json == {"P1": "자리를 하나로\n경력 3년 이상"}`, targets 앞 두 줄이 P1·P2, `res["다시"] == 1`.
  - `test_pipeline_tasks.py` 의 기존 `test_daily_collect_writes_targets_check_and_excluded` 기대 dict 에 `"다시": 0` 을 더한다.
  - `test_pipeline_tasks.py::test_daily_report_counts_sent_back` — `daily_report(run_dir, {"new": 2, "pending": 3, "다시": 1}, {}, 0.0)` 글에 `밀린 공고 3 (검토 다시 1)` 이 있고, `"다시": 0` 이면 `(검토 다시` 가 없다.
  - `test_run_model.py::test_feedback_goes_into_input_and_hash`, `::test_posting_inputs_reads_feedback` — 보류 stash 의 같은 이름 시험을 키 이름 `feedback` 그대로 가져온다. 두 번째 시험에 "`feedback.json` 이 없으면 모든 공고 `feedback == ''`" 단언을 더한다(③).

- [ ] **Step 2: 실패 확인** — `pytest tests/test_pipeline_tasks.py tests/test_run_model.py -q` → 새 시험 FAIL

- [ ] **Step 3: 고치기**
  - `step_collect`: `write_targets` 뒤에 `feedback.json` 을 쓴다(① 일 때만, ③ 은 `pending` 이 비어 `{}` — 써도 된다). 결과 dict 에 `"다시": sum(1 for r in pending if r.get("feedback"))`. 설명의 '밀린 공고' 정의도 고친다.
  - `daily_report` 수집 줄: `밀린 공고 {pending}` 뒤에 `다시` 가 1 이상이면 ` (검토 다시 {n})`.
  - `extract_skills`: `FEEDBACK` 상수, `posting_inputs` 가 파일이 있으면 읽어 `feedback` 을 싣고(없으면 `''`), `llm_input` 에 위 문구. `extract_one` 의 두 번째 부름도 같은 `inp` 를 쓰므로 따로 고칠 것 없음.

- [ ] **Step 4: 통과 확인** — `pytest tests/test_pipeline_tasks.py tests/test_run_model.py tests/test_extract_dictionary.py -q` → PASS

- [ ] **Step 5: 커밋** — `feat: 검토 '다시' 피드백을 feedback.json → LLM 입력 끝에, 결과 알림에 '다시' 수`

### Task 4: 같은 피드백으로 다시 보내도 저장

**Files:**
- Modify: `job-skill/db_load.py` (`insert_run` 의 '이미 넣은 결과' 비교)
- Test: `job-skill/tests/test_review_decision.py`

**Interfaces:**
- Consumes: Task 1 의 값, `tests/test_db_queries.py` 의 `_write_run(run_dir, page_text)`, `_load(run_dir, db_url)`.

- [ ] **Step 1: 실패하는 시험 쓰기** — 보류 stash 의 `test_load_saves_rerun_after_sent_back` 를 새 값으로: 첫 저장 뒤 `UPDATE extraction_run SET review_result='다시', review_feedback='자리를 하나로', reviewed_at=now()`, 같은 결과 파일로 `_load` 두 번 → `SELECT review_result, is_current FROM extraction_run ORDER BY id` == `[("다시", False), (None, True)]`.

- [ ] **Step 2: 실패 확인** — FAIL(두 번째 저장이 '이미 있음'으로 건너뜀 → 한 줄)

- [ ] **Step 3: 고치기** — 비교 SQL 에 `AND review_result IS DISTINCT FROM '다시'` 를 더하고, 이유를 한 줄 주석으로(같은 피드백으로 또 돌려보내면 입력 지문이 같다).

- [ ] **Step 4: 통과 확인** — `pytest tests/test_review_decision.py tests/test_db_load.py tests/test_insert_run.py -q` → PASS

- [ ] **Step 5: 커밋** — `fix: '다시'로 돌려보낸 결과와 입력이 같아도 새 결과로 저장`

### Task 5: 문서와 그림

**Files:**
- Modify: `job-skill/docs/physical-design.md` (extraction_run 표의 두 줄 → 세 줄, '사람 검토' 설명, 색인 표의 검토 목록 설명)
- Modify: `job-skill/docs/erd.svg`, `job-skill/docs/erd-physical.svg` (+ 같은 이름 `.png` 다시 만들기)
- Modify: `README.md`(맨 위) 의 팀원 권한 SQL 에 `GRANT UPDATE (review_result, review_feedback, reviewed_at) ON extraction_run TO team;` 한 줄과 이유

- [ ] **Step 1: physical-design.md** — 칸 표: `확인 결과 review_result text 정상/제외/다시` , `검토 피드백 review_feedback text 다시일 때 꼭`, 확인 시각은 그대로. 표 아래에 세 단어의 뜻과 그 뒤(설계 문서 '목표' 표와 같은 내용), 웹이 쓰는 규칙 두 줄(검토 목록 = 현재 결과 + 검토 사유 있음 + 검토 결과 빔 / '제외'는 웹에 보이지 않음), 팀원은 세 칸만 쓸 수 있음.
- [ ] **Step 2: 그림** — 두 SVG 의 추출 실행 상자에서 `확인 결과`/`review_result` 줄 아래에 `검토 피드백`/`review_feedback`(`text?`) 줄을 더한다. 줄 간격 24, 아래 줄과 상자 높이·그 아래 요소를 24 씩 내린다(ce74734 에서 모집 단위에 직무 칸을 더한 방식). 그림 스타일은 흰 바탕·검은 선 그대로. PNG 는 Edge headless 로 SVG 와 같은 크기로 다시 만든다(`msedge --headless --screenshot=<png> --window-size=<w>,<h> <svg>`).
- [ ] **Step 3: 눈으로 확인** — 새 PNG 두 장을 열어 줄이 겹치거나 잘리지 않았는지 본다.
- [ ] **Step 4: 커밋** — `docs(erd): 추출 실행에 검토 피드백 칸, 검토 결과를 정상·제외·다시로(논리·물리 ERD, 물리 설계, 팀원 권한)`

### Task 6: 전체 확인과 RDS 적용

- [ ] **Step 1: 전체 시험** — Docker career-db 를 켜고 `cd job-skill && PYTHONIOENCODING=utf-8 py -3.12 -m pytest tests -q` → 모두 통과(건너뜀은 airflow.sdk 1개뿐). Docker 를 켤 수 없으면 push 뒤 CI 결과로 확인하고 그렇게 보고한다.
- [ ] **Step 2: 사용자에게 묻기** — "RDS 에 010 을 적용할까요?" 허락을 받으면 `career` 계정으로 010 파일만 직접 실행하고, 다음을 읽어서 확인: 두 제약 정의, `has_column_privilege('team','public.extraction_run','review_result','UPDATE')` = true, `has_column_privilege('team','public.extraction_run','is_current','UPDATE')` = false.
- [ ] **Step 3: 보고** — 바뀐 것, 시험 결과, RDS 적용 여부, 팀원에게 전할 것(웹을 새 칸으로 바꾸기 → 그 뒤 자기 표·008·009·sync SQL 지우기)을 짧게.
