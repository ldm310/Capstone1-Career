# Airflow DAG 구현 계획 (채용공고 역량 추출 자동화)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사람인 백엔드·데이터 엔지니어 공고(0~3년)를 Airflow DAG 3개(①매일 수집, ②3일마다 수정 확인, ③일회성 전체 수집)가 로컬 Docker에서 자동으로 수집→OCR→추출→DB 저장하고 Slack으로 알리게 한다.

**Architecture:**
- **기존 스크립트는 그대로 쓴다.** `fetch_images.py`, `dump_paddle_boxes.py`, `section_split.py`, `extract_skills.py`, `db_load.py`를 실행(run) 폴더마다 `OCR_DATA_DIR=<run 폴더>`로 **subprocess** 실행한다.
  - 이유: `common.py`가 import할 때 경로를 정하므로, 실행 폴더마다 새 프로세스가 필요하다.
- **새로 만드는 모듈은 실행 폴더를 인자로 받는다.** 수집(`collect.py`), 수정 확인(`recheck.py`), DB 조회(`db_queries.py`), Slack(`notify.py`), 태스크 함수(`pipeline_tasks.py`)
- **Airflow 3.3.2 (LocalExecutor):** 별도 Docker 묶음(`airflow/`)에서 DAG 파일 하나로 세 DAG를 정의하고, 태스크는 `pipeline_tasks` 함수를 부른다.

**Tech Stack:** Python 3.12, Apache Airflow 3.3.2 (`apache/airflow:3.3.2-python3.12`), PostgreSQL 17.6, psycopg 3.2.3, openai 2.7.2, paddleocr 3.7.0 + paddlepaddle-gpu 3.2.2(cu126), pytest, Docker Desktop(WSL2, GPU).

**Spec:** `job-skill/docs/superpowers/specs/2026-10-27-airflow-dags-design.md` (그림: `job-skill/docs/dag-backfill.png`, `dag-daily.png`, `dag-recheck.png`)

모든 경로는 `job-skill/` 기준이다. 명령은 `job-skill/`에서 실행한다(PowerShell).

## Global Constraints

- **시간대:** 모든 일정·하루 경계는 **KST(Asia/Seoul)**
- **일정:** ① `daily_collect` 매일 **00:00**, ② `recheck_postings` **3일마다 12:00**, ③ `backfill_once`는 일정 없음(수동 1회)
- **켜는 순서:** ①·②는 처음에 꺼진 상태(일시정지)다. 사용자가 ③을 직접 실행하고 끝나면 ①·②를 켠다. 실행 조건 확인·완료 기록 태스크는 없다.
- **대상:** 사람인 `cat_kewd=84`(백엔드), `83`(데이터엔지니어)만, 최소 요구 연수 ≤ 3(`sample_random.min_years`), 교육생 제외. **4년 이상은 본문도 요청하지 않는다.**
- **새 공고 판단:** 최신순 목록에서 **이미 아는 공고번호가 연속 5개** 나오면 멈추고, 그 앞의 처음 보는 공고만 새 공고로 본다.
- **LLM:** `gpt-5.6-luna`, reasoning `low`, 예시 답안 포함(`--examples`), 결과 폴더 태그 `-ex`
- **비용 상한:** 하루 **$5**(KST 하루, ①+② 합산, `extraction_run.cost_usd` 기준). ③은 한 번 실행에 **$10**. 넘으면 추출을 멈추고 Slack으로 알린다.
- **사람인 요청:** 요청 사이 **1.2초 이상**(`fetch_images.get`의 throttle), UA는 `fetch_images.UA`(프로젝트 이름). 브라우저로 꾸미지 않는다.
- **OCR:** **GPU로만** 돌린다. GPU를 못 쓰면 CPU로 바꾸지 말고 태스크를 실패시켜 Slack으로 알린다.
- **Slack:** 웹훅은 `.env`의 `SLACK_WEBHOOK_URL`이다. 메시지에는 **숫자·상태·오류 종류만** 넣고, 공고 제목·회사·본문은 넣지 않는다.
- **비밀:** `.env`(DB 비밀번호, Slack 웹훅)는 git에 올리지 않는다. `OPENAI_API_KEY`는 노트북 환경변수에서 넘긴다.
- **데이터:** 공고 원본·OCR·추출 결과(`data/`)는 git에 올리지 않는다. 시험용 HTML은 **지어낸 내용**으로 만든다.
- **DB:** 서빙 DB `career-db`(`localhost:5433`, DB·계정 `career`)를 쓰고, 표는 `job` 스키마에 둔다. Airflow 컨테이너에서는 `host.docker.internal:5433`으로 접속한다.
- **컨테이너:** Airflow 묶음은 api-server · scheduler · dag-processor · airflow-db 4개 + airflow-init(1회)이다. triggerer·Celery·Redis·Flower·Grafana는 넣지 않는다. Docker 메모리 한계는 8GB다.
- **커밋:** 메시지에 Claude 공동 작성자 줄을 넣지 않는다. 브랜치는 `feature/job-skill`이다.

## Review Focus

- **새 공고가 0건인 날(전부 아는 공고):** 어느 단계도 죽지 않고, 결과 알림에 "새 공고 0"이 가야 한다.
  - 지금 `extract_skills.main`은 입력이 0건이면 0으로 나눠서 죽는다. → Task 3, Task 6 시험
- **목록 쪽 요청이 실패(HTTP 오류·시간 초과):** "목록 끝"으로 착각해 조용히 0건으로 끝내면 안 되고, 태스크를 실패시켜(재시도·Slack) 알려야 한다. → Task 2 시험
- **마감일 글이 예상 밖("상시채용", "채용시 마감", "오늘마감", 비어 있음):** 죽지 않고 마감일을 비워 둔다. 연말에 "~01/05"는 다음 해로 읽는다. → Task 2 시험
- **비용 상한에 걸려 중간에 멈춤:**
  - 추출된 것까지만 DB에 넣고, 나머지 공고도 공고로는 저장해 다음 ① 실행 때 "밀린 공고"로 다시 추출한다.
  - Slack 상한 알림은 한 번만 간다.
  - → Task 3, Task 1, Task 6 시험
- **Docker 안에서 GPU가 안 보임:** OCR 태스크가 CPU로 돌지 않고 바로 실패하며 Slack으로 알린다. → Task 6 시험

---

### Task 1: DB 변경 — 본 공고번호 표, 진행 공고 뷰, 추출 원본 해시, 조회 함수

**Files:**
- Modify: `db/schema.sql` (새 설치용)
- Create: `db/migrations/001_airflow.sql` (지금 `career-db`에 적용, 여러 번 돌려도 안전하게 `IF NOT EXISTS`/`OR REPLACE`)
- Modify: `db_load.py` (`upsert_posting`, `insert_run`, `cmd_load`)
- Create: `db_queries.py`
- Create: `tests/conftest.py`, `tests/test_db_queries.py`, `requirements-dev.txt`

**Interfaces:**
- Produces (DB):
  - 표 `job.listing_seen(site text, site_posting_no text, reason text NOT NULL, first_seen_at timestamptz DEFAULT now(), PRIMARY KEY(site, site_posting_no))` — 버린 공고(4년 이상·교육생·경력 조건 모름)만 기록한다.
  - 뷰 `job.open_posting` = `posting WHERE status='진행' AND (deadline IS NULL OR deadline >= current_date)`
  - 칸 `job.extraction_run.raw_hash char(64)` — 추출에 쓴 공고 원본 해시. 마이그레이션에서 기존 줄은 `posting.raw_hash`로 채운다.
- Produces (`db_queries.py`, 모두 `conn: psycopg.Connection`을 받고, search_path는 `job`):
  - `known_posting_nos(conn) -> set[str]` — `posting.site_posting_no` ∪ `listing_seen.site_posting_no` (site='사람인')
  - `record_excluded(conn, rows: list[tuple[str, str]]) -> int` — (공고번호, 이유) 넣기, 겹치면 무시
  - `pending_postings(conn) -> list[dict]` — 진행 공고(뷰) 가운데 **현재 추출 실행이 없거나** 그 `raw_hash`가 `posting.raw_hash`와 다른 공고
    - 돌려주는 줄: `{"rec_idx","company","title","role","career","deadline","kind","text_chars","images"}` (`targets.tsv`와 같은 칸, `kind`·`text_chars`·`images`는 빈 문자열)
  - `open_postings(conn) -> list[dict]` — 뷰의 공고, 위 칸 + `"raw_hash"`
  - `mark_closed(conn, nos: list[str]) -> int` — `status='마감'`
  - `touch_checked(conn, nos: list[str]) -> int` — `last_checked_at=now()`
  - `day_cost(conn, day: datetime.date) -> tuple[float, int]` — KST 그날 `extraction_run`의 비용 합과 줄 수
- Produces (`db_load.py`):
  - `targets.tsv`의 `deadline` 칸(`YYYY-MM-DD` 또는 빈칸)을 `posting.deadline`에 넣는다. 칸이 아예 없는 옛 `targets.tsv`(sample3)는 빈칸으로 본다.
  - `insert_run`이 `raw_hash`를 채운다.
  - `load(run: str) -> dict[str, int]`: 기존 `cmd_load` 본문
    - 추출 결과 폴더가 없어도 `sys.exit` 하지 않고 공고·이미지만 넣는다.
    - `targets.tsv`가 비었으면 0을 돌려준다.
  - `cmd_load`는 `load`를 불러 출력만 한다.

- [ ] **Step 1: 시험 도구 준비**
  - `requirements-dev.txt`에 `pytest==8.4.2`를 적고 `py -3.12 -m pip install -r requirements-dev.txt`로 설치한다.
  - `tests/conftest.py`의 `db` fixture를 만든다.
    - `.env`의 `DATABASE_URL`(career@localhost:5433)로 접속해 `job_test_<무작위>` DB를 만든다.
    - `db/schema.sql`과 `db/migrations/*.sql`을 차례로 적용한다.
    - `search_path=job` 연결을 넘겨주고, 끝나면 DB를 지운다.
    - `career-db`에 접속할 수 없으면 `pytest.skip`한다.

- [ ] **Step 2: 실패하는 시험 작성 — `tests/test_db_queries.py`**
  - `test_known_includes_postings_and_excluded`: 공고 1건(`'100'`) + `record_excluded([('200','4년 이상')])` → `known_posting_nos == {'100','200'}`, 같은 줄을 다시 넣으면 0을 돌려준다.
  - `test_open_posting_view_hides_past_deadline`: 마감일 어제 / 오늘 / NULL / status='마감' 4건 → `open_postings`에는 "오늘"과 "NULL" 2건만 나온다.
  - `test_pending_when_no_run_or_hash_changed`:
    - 실행 없는 공고 A → pending
    - 현재 실행 `raw_hash`가 같은 B → 아님
    - 공고 해시가 바뀐 C → pending
  - `test_day_cost_uses_kst_boundaries`: `run_at`이 `2026-10-27 23:30+09:00`($0.10)과 `2026-10-28 00:10+09:00`($0.20) → `day_cost(2026-10-27) == (0.10, 1)`
  - `test_mark_closed_and_touch`: `mark_closed(['A'])` → A는 뷰에서 빠진다. `touch_checked(['B'])` → `last_checked_at`이 바뀐다.

- [ ] **Step 3: 시험 실행 → 실패 확인**
  - Run: `py -3.12 -m pytest tests/test_db_queries.py -v`
  - Expected: FAIL (`db_queries` 모듈 없음)

- [ ] **Step 4: 구현**
  - 스키마·마이그레이션(위 DB 정의, 한글 COMMENT 포함)
  - `db_queries.py`: 연결은 `db_load.connect()`를 쓴다. KST 하루 경계는 `zoneinfo.ZoneInfo("Asia/Seoul")`로 계산한다.
  - `db_load.py` 변경(위 Produces)

- [ ] **Step 5: 시험 실행 → 통과 확인**
  - Run: `py -3.12 -m pytest tests/test_db_queries.py -v`
  - Expected: 5 passed

- [ ] **Step 6: 지금 `career-db`에 마이그레이션 적용 + sample3 다시 넣어 확인**
  - Run: `Get-Content db/migrations/001_airflow.sql -Raw | docker exec -i career-db psql -U career -d career -v ON_ERROR_STOP=1`
  - Run: `$env:OCR_DATA_DIR="sample3"; py -3.12 db_load.py load --run gpt-5.6-luna-ex-chk`
  - Expected: 오류 없음, 마지막 줄에 `추출 실행(새로) 0 · 추출 실행(이미 있음) 19`. `SELECT count(*) FROM job.extraction_run WHERE raw_hash IS NULL` = 0

- [ ] **Step 7: 커밋** — `git add db/ db_load.py db_queries.py tests/ requirements-dev.txt; git commit -m "feat: DB에 본 공고번호 표·진행 공고 뷰·추출 원본 해시 추가"`

---

### Task 2: 공고 목록 수집 — 마감일, 연속 5개 멈춤, 버린 공고

**Files:**
- Create: `collect.py`
- Create: `tests/fixtures/list_page.html` (지어낸 회사·제목, 실제 사람인 목록의 HTML 구조만 흉내)
- Create: `tests/test_collect.py`

**Interfaces:**
- Consumes: `sample_random.LIST`, `sample_random.ROLES`, `sample_random.parse_list`, `sample_random.min_years`, `sample_random.TRAINING`, `fetch_images.get`, `sample_postings.body_stats`
- Produces:
  - `TARGET_FIELDS = ["rec_idx","company","title","role","career","deadline","kind","text_chars","images"]`
  - `class ListFetchError(RuntimeError)`
  - `parse_items(page: str) -> list[dict]` — `parse_list` 결과 + `"deadline_text"`(목록의 마감일 글 그대로)
  - `parse_deadline(text: str, today: datetime.date) -> datetime.date | None`
  - `eligible(career: str) -> tuple[bool, str]` — `(True, "")` 또는 `(False, "4년 이상" | "교육생" | "경력 조건 모름")`
  - `select_new(items: list[dict], known: set[str], stop_after: int = 5) -> tuple[list[dict], bool]` — (멈춘 곳 앞의 처음 보는 공고, 멈췄는지)
  - `collect_list(run_dir: str, known: set[str], get=fetch_images.get, max_pages: int = 40, stop_after: int = 5, max_new: int | None = None, today: datetime.date | None = None) -> dict`
    - 돌려주는 값: `{"targets": list[dict], "excluded": list[tuple[str,str]], "listed": int, "stopped": dict[str,bool]}`
    - `<run_dir>/targets.tsv`를 쓴다. 겹친 공고는 먼저 본 직무 하나로만 넣는다.
  - `write_targets(run_dir: str, rows: list[dict]) -> None`, `read_targets(run_dir: str) -> list[dict]`
  - `classify_targets(run_dir: str) -> dict[str, int]` — 공고 원본 수집 뒤에 쓴다.
    - `pages/`의 본문으로 `kind`·`text_chars`·`images`를 채운다. 규칙은 `sample_random`과 같다(글자 < 100 이고 이미지 ≥ 1 → 이미지, 이미지 0 → 글, 나머지 → 섞임).
    - 본문이 없는 공고는 `targets.tsv`에서 뺀다.
    - 돌려주는 값: `{"글": n, "이미지": n, "섞임": n, "본문 없음": n}`

- [ ] **Step 1: 실제 목록의 마감일 HTML 확인 (사람인 요청 1번)**
  - `fetch_images.get(sample_random.LIST.format(code="84", page=1))`로 받은 HTML은 **scratchpad에만 저장**한다(저장소 X).
  - 공고 하나(`<div id="rec-…" class="list_item">`) 안에서 마감일("~ 11/15(토)" 같은 글)이 든 요소를 찾는다.
  - 그 구조를 흉내 내 **지어낸 공고 7건**으로 `tests/fixtures/list_page.html`을 만든다.
    - 0~3년 4건, "경력 5년↑" 1건, 교육생 1건, "상시채용" 마감 1건

- [ ] **Step 2: 실패하는 시험 작성 — `tests/test_collect.py`**
  - `test_parse_items_reads_fixture`: 7건, 공고번호·경력·`deadline_text`가 fixture와 같다.
  - `test_parse_deadline_cases`: `today=date(2026,10,28)`
    - `"~ 11/15(토)"` → `2026-11-15`
    - `"~ 01/05(월)"` → `2027-01-05`
    - `"오늘마감"` → `2026-10-28`
    - `"내일마감"` → `2026-10-29`
    - `"상시채용"`, `"채용시 마감"`, `""` → `None`
  - `test_eligible`: `"신입 · 경력"` → `(True,"")`, `"경력 5년↑ · 정규직"` → `(False,"4년 이상")`, `"신입 · 교육생"` → `(False,"교육생")`
  - `test_select_new_stops_after_five_known`: 공고번호 `[10,9,8,7,6,5,4,3]`, known=`{7,6,5,4,3}` → 새 공고 `[10,9,8]`, 멈춤 True
  - `test_select_new_ignores_short_known_runs`: `[10,9,8,7,6,5,4]`, known=`{9,8}` → 새 공고 `[10,7,6,5,4]`, 멈춤 False
  - `test_select_new_all_known_is_empty`: 전부 known(6개) → `[]`, True (같은 날 다시 돌려도 0건 = 멱등)
  - `test_collect_list_filters_and_writes_targets`: 가짜 `get`이 fixture를 첫 쪽으로 주고 둘째 쪽은 빈 목록
    - `targets.tsv`에 0~3년만(마감일 칸 ISO), `excluded`에 4년 이상·교육생
    - 4년 이상 공고의 본문 요청이 없다(가짜 get에 `relay` 주소 호출 0번)
  - `test_collect_list_raises_on_list_error`: 가짜 `get`이 `(500, "", b"")` → `ListFetchError`
  - `test_classify_targets`: 가짜 `pages/`에 글 공고·이미지 공고·본문 없는 공고 → `kind` 채움, 본문 없는 줄 빠짐

- [ ] **Step 3: 시험 실행 → 실패 확인** — `py -3.12 -m pytest tests/test_collect.py -v` → FAIL(모듈 없음)

- [ ] **Step 4: 구현** — `collect.py` (위 Interfaces). 쪽마다 `select_new`를 이어서 적용하고(연속 수는 쪽을 넘어 이어진다), 멈추거나 빈 쪽이 나오면 그 직무를 끝낸다. `max_new`에 닿으면 끝낸다.

- [ ] **Step 5: 시험 실행 → 통과** — `py -3.12 -m pytest tests/test_collect.py -v` → 9 passed

- [ ] **Step 6: 커밋** — `git add collect.py tests/; git commit -m "feat: 공고 목록 수집(마감일·연속 5개 멈춤·버린 공고)"`

---

### Task 3: LLM 추출 비용 상한 + 0건 처리

**Files:**
- Modify: `extract_skills.py` (`run_model`, `main`)
- Create: `tests/test_extract_budget.py`

**Interfaces:**
- Produces:
  - `run_model(client, model, effort, inputs, examples=False, tag="", max_usd: float | None = None) -> dict`
    - 새로 LLM을 부르기 **전에** 이번 실행에서 새로 쓴 비용(`cost_usd` 합)이 `max_usd` 이상이면 멈춘다.
    - stats에 `"stopped": bool`, `"spent_new": float`, `"left": int`를 더한다.
    - 멈췄으면 `<EX>/_budget.json` = `{"stopped": true, "spent": float, "limit": float, "left": int}`를 쓴다.
    - 이미 결과 파일이 있는 공고는 비용 없이 건너뛴다(지금 동작 유지).
  - CLI `--max-usd FLOAT`(없으면 상한 없음)
  - 입력이 0건이면 OpenAI 클라이언트를 만들지 않고 `_stats.json`에 `[]`을 쓰고 정상 종료(코드 0)한다.

- [ ] **Step 1: 실패하는 시험 작성** — 가짜 클라이언트(호출마다 입력 10,000 / 출력 1,000 토큰 = luna 기준 $0.0032)
  - `test_stops_before_exceeding_budget`: 공고 5건, `max_usd=0.006`
    - LLM 호출 2번 뒤 멈춘다(2번째 뒤 누적 $0.0064 ≥ 상한).
    - `stopped=True`, `left=3`, `_budget.json`이 있다.
  - `test_no_budget_runs_all`: `max_usd=None` → 5번 호출, `stopped=False`, `_budget.json` 없음
  - `test_cached_results_cost_nothing`: 결과 파일 3개가 미리 있고 `max_usd=0.004` → 새 호출 2번까지만(1번 뒤 $0.0032 < 0.004, 2번 뒤 멈춤)
  - `test_main_with_zero_inputs_exits_cleanly`: 머리줄만 있는 `targets.tsv`를 둔 빈 run 폴더(OCR_DATA_DIR)로 subprocess 실행 → 종료 코드 0, `_stats.json` == `[]`

- [ ] **Step 2: 실패 확인** — `py -3.12 -m pytest tests/test_extract_budget.py -v` → FAIL

- [ ] **Step 3: 구현** (위 Interfaces). 지시문·표준화·검사 로직은 바꾸지 않는다.

- [ ] **Step 4: 통과 확인** — 같은 명령 → 4 passed. 기존 가짜 LLM 시험도 다시 돌려 확인한다.
  - `scratchpad/test_run_model.py`를 `tests/test_run_model.py`로 옮겨 pytest 형식으로 바꾼다. → 다시 부르기·표준화 전 답 저장 통과

- [ ] **Step 5: 커밋** — `git commit -m "feat: LLM 추출 비용 상한(--max-usd)과 0건 처리"`

---

### Task 4: Slack 알림

**Files:**
- Create: `notify.py`, `tests/test_notify.py`

**Interfaces:**
- Produces:
  - `send(text: str) -> bool` — 웹훅은 환경변수 `SLACK_WEBHOOK_URL`, 없으면 `.env`에서 읽는다. 실패해도 예외를 던지지 않고 False를 돌려주며 로그만 남긴다.
  - `msg_result(dag_label: str, counts: dict) -> str` — 예: `"✅ 매일 수집 완료 · 새 공고 52 · 추출 52 · 확인 필요 2 · 오늘 비용 $0.21"`. 넘겨받은 키 순서대로 `이름 값`을 잇는다. 비용 키(이름에 "비용")는 `$0.00` 형식이다.
  - `msg_failure(dag_id: str, task_id: str, try_number: int, exc: BaseException | None) -> str` — `"❌ {dag_id} · {task_id} 실패 ({try_number}번째 시도) · {예외 이름}: {메시지 앞 200자}"`
  - `msg_budget(dag_label: str, spent: float, limit: float, left: int) -> str` — `"⚠️ {dag_label}: 비용 상한 ${limit:.2f} 도달로 LLM 추출 멈춤 · 쓴 비용 ${spent:.2f} · 남은 공고 {left}건은 다음 실행 때"`
  - `msg_daily_cost(day: datetime.date, usd: float, runs: int) -> str` — `"💰 {M}월 {D}일 LLM 비용 ${usd:.2f} (추출 {runs}건)"`
  - `on_failure(context: dict) -> None` — Airflow `on_failure_callback`. `context["ti"]`의 dag_id·task_id·try_number와 `context.get("exception")`으로 `send(msg_failure(...))`

- [ ] **Step 1: 실패하는 시험 작성**
  - `test_msg_result_format`: `msg_result("매일 수집", {"새 공고": 52, "추출": 52, "확인 필요": 2, "오늘 비용": 0.214})` == `"✅ 매일 수집 완료 · 새 공고 52 · 추출 52 · 확인 필요 2 · 오늘 비용 $0.21"`
  - `test_msg_failure_truncates`: 메시지 500자 예외 → 결과에 앞 200자만 들어간다.
  - `test_msg_budget_and_daily_cost`: `msg_budget("매일 수집", 5.02, 5.0, 12)`에 `"$5.00"`, `"$5.02"`, `"12건"`이 있다. `msg_daily_cost(date(2026,10,27), 0.413, 104)` == `"💰 10월 27일 LLM 비용 $0.41 (추출 104건)"`
  - `test_send_posts_json_to_webhook`: `urllib.request.urlopen`을 가짜로 바꿔 받은 본문이 `{"text": ...}`인지, 주소가 env 값인지 확인한다.
  - `test_send_without_webhook_returns_false`: env·`.env` 모두 없음(임시 폴더) → False, 예외 없음

- [ ] **Step 2: 실패 확인** — `py -3.12 -m pytest tests/test_notify.py -v` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — 5 passed
- [ ] **Step 5: 커밋** — `git commit -m "feat: Slack 알림(실패·상한·결과·하루 비용)"`

---

### Task 5: 수정 확인 — 변경 감지

**Files:**
- Create: `recheck.py`, `tests/test_recheck.py`

**Interfaces:**
- Consumes: `db_load.content_hash(page, rid)`, `fetch_images.RELAY`, `fetch_images.get`, `collect.write_targets`, `collect.TARGET_FIELDS`
- Produces:
  - `detect_changes(run_dir: str, rows: list[dict], get=fetch_images.get) -> dict[str, list[str]]` — `rows`는 `db_queries.open_postings` 결과
    - 공고마다 본문을 받아 셋으로 나눈다.
      - 본문이 없거나 HTTP 오류(404 등)이거나 `user_content`가 없음 → `"closed"`
      - `content_hash`가 `raw_hash`와 다름 → `"changed"`
      - 같음 → `"unchanged"`
    - changed는 `<run_dir>/pages/<번호>.html`로 저장하고 `targets.tsv`에 쓴다(rows의 targets 칸 그대로).
    - `<run_dir>/changes.json`에 결과를 쓰고 돌려준다.
  - 연결 실패(status None)는 `closed`로 치지 않는다. 그 공고만 건너뛰고 `"error"` 목록에 넣는다(사람인 일시 장애로 공고를 마감시키지 않게).

- [ ] **Step 1: 실패하는 시험 작성** — 가짜 get
  - `test_detect_changes_splits_three_ways`:
    - A: 같은 본문 → unchanged
    - B: 글자 한 줄 다른 본문 → changed, `pages/B.html`과 `targets.tsv`에 B
    - C: `(404,"",b"")` → closed
  - `test_font_color_noise_is_not_a_change`: 같은 본문에서 `<font color="#xxxxxx"></font>` 색 값만 다르면 unchanged
  - `test_connection_error_is_not_closed`: `(None,"",b"")` → `error`에 들어가고 closed에는 없다.

- [ ] **Step 2: 실패 확인** — `py -3.12 -m pytest tests/test_recheck.py -v` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — 3 passed
- [ ] **Step 5: 커밋** — `git commit -m "feat: 수정 확인(본문 지문 비교로 변경·마감 감지)"`

---

### Task 6: 태스크 함수 — 실행 폴더·단계 실행·GPU 확인·요약

**Files:**
- Create: `pipeline_tasks.py`, `tests/test_pipeline_tasks.py`
- Modify: `fetch_images.py` — 이미지도 이미 받은 파일(`{rid}_{seq}.*`)이 있으면 다시 받지 않는다(본문 파일 건너뛰기와 같게).
- Modify: `.gitignore` — `data/`, `airflow/logs/` 추가

**Interfaces:**
- Consumes: Task 1~5의 함수, `notify.send/msg_budget`
- Produces (상수):
  - `MODEL = "gpt-5.6-luna"`, `TAG = "-ex"`, `RUN_NAME = "gpt-5.6-luna-ex"`
  - `DAILY_LIMIT = 5.0`, `BACKFILL_LIMIT = 10.0`
- Produces (함수, 모두 `run_dir`은 `job-skill` 기준 상대 경로):
  - `run_dir_for(dag_id: str, run_id: str) -> str` — `data/runs/<dag_id>/<run_id에서 영숫자·_.- 외 글자를 _로 바꾼 것>`
  - `run_script(script: str, args: list[str], run_dir: str) -> None` — `subprocess.run([sys.executable, script, *args], cwd=HERE, env={..., "OCR_DATA_DIR": run_dir}, check=True)`
  - `step_collect(run_dir: str, include_pending: bool, max_new: int | None = None) -> dict` — `known_posting_nos` → `collect_list` → `record_excluded`. `include_pending`이면 `pending_postings`를 targets에 더한다(공고번호로 중복 제거). 돌려주는 값: `{"new": n, "pending": n, "excluded": n}`
  - `step_fetch_raw(run_dir: str) -> dict` — targets가 0이면 아무것도 안 함. 아니면 `fetch_images.py` 실행 → `classify_targets`
  - `class GpuUnavailable(RuntimeError)`, `check_gpu() -> None` — subprocess로 `import paddle; assert paddle.device.cuda.device_count() > 0`. 실패하면 `GpuUnavailable`
  - `step_ocr(run_dir: str) -> None` — 이미지가 0장(manifest에 파일 없음)이면 아무것도 안 함. 아니면 `check_gpu()` 뒤 `dump_paddle_boxes.py --gpu`
  - `step_filter(run_dir: str) -> None` — 이미지 0장이면 아무것도 안 함. 아니면 `section_split.py --paddle-only`
  - `budget_left(conn, limit: float, day: datetime.date) -> float` — `max(0, limit - day_cost(conn, day)[0])`
  - `step_extract(run_dir: str, budget_usd: float, dag_label: str) -> dict`
    - targets 0건이면 아무것도 안 함.
    - `budget_usd <= 0`이면 LLM 없이 `{"stopped": True}`를 돌려주고 상한 알림을 보낸다.
    - 아니면 `extract_skills.py --models gpt-5.6-luna --effort low --examples --tag -ex --max-usd {budget_usd}`
    - `_budget.json`이 있으면 `notify.send(msg_budget(...))`를 한 번 보낸다.
  - `step_load(run_dir: str) -> dict` — targets 0건이면 아무것도 안 함. 아니면 `db_load.py load --run gpt-5.6-luna-ex`
  - `summary(run_dir: str) -> dict` — `{"새 공고": targets 수, "추출": 결과 파일 수, "확인 필요": review_reasons가 빈 목록이 아닌 결과 수, "비용": 결과 파일 cost_usd 합}`

- [ ] **Step 1: 실패하는 시험 작성** — `run_script`를 가짜로 바꿔 호출을 기록한다.
  - `test_run_dir_for_sanitizes`: `run_dir_for("daily_collect", "scheduled__2026-10-28T00:00:00+09:00")` == `"data/runs/daily_collect/scheduled__2026-10-28T00_00_00_09_00"`
  - `test_empty_run_skips_everything`: 빈 targets로 `step_fetch_raw`·`step_ocr`·`step_filter`·`step_extract`·`step_load` → `run_script` 호출 0번, `summary` == `{"새 공고":0,"추출":0,"확인 필요":0,"비용":0.0}`
  - `test_ocr_fails_without_gpu`: 이미지 1장 있는 run 폴더 + `check_gpu`가 `GpuUnavailable`를 던짐 → `step_ocr`가 예외를 그대로 던지고 `dump_paddle_boxes.py` 호출 0번
  - `test_extract_passes_budget_and_alerts_once`: `run_script`가 `_budget.json`을 만들어 두게 함 → 인자에 `--max-usd 1.5`, `notify.send` 1번
  - `test_extract_with_no_budget_left_skips_llm`: `budget_usd=0` → `run_script` 호출 0번, `notify.send` 1번
  - `test_fetch_images_skips_existing_image`: 이미 `{rid}_1.png`가 있으면 가짜 `get`에 그 이미지 주소 호출 0번(`fetch_images.main`을 임시 run 폴더로)

- [ ] **Step 2: 실패 확인** — `py -3.12 -m pytest tests/test_pipeline_tasks.py -v` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `py -3.12 -m pytest -v` → 지금까지 모든 시험 통과
- [ ] **Step 5: 커밋** — `git commit -m "feat: Airflow 태스크 함수(실행 폴더·단계 실행·GPU 확인·요약)"`

---

### Task 7: Airflow Docker 묶음 (이미지·compose·GPU)

**Files:**
- Create: `airflow/Dockerfile`, `airflow/requirements-airflow.txt`, `airflow/docker-compose.yml`
- Modify: `.env.example` — `AIRFLOW_DB_PASSWORD=` 줄 추가. 실제 `.env`에도 무작위 값을 넣는다(파이썬 `secrets.token_urlsafe(18)`).

**Interfaces:**
- Produces:
  - **이미지:** 컨테이너 안 `/opt/airflow/job-skill` = 노트북 `job-skill/`(연결 폴더), `PYTHONPATH=/opt/airflow/job-skill`
  - **compose:** 프로젝트 이름 `career-airflow`, 서비스 `airflow-db`, `airflow-init`, `airflow-apiserver`, `airflow-scheduler`, `airflow-dag-processor`
  - **연결 폴더:**
    - `../` → `/opt/airflow/job-skill`
    - `./dags` → `/opt/airflow/dags`
    - `./logs` → `/opt/airflow/logs`
    - `../data/paddlex` → `/home/airflow/.paddlex` (모델 캐시)

- [ ] **Step 1: 공식 compose를 바탕으로 줄이기**
  - `https://airflow.apache.org/docs/apache-airflow/3.3.2/docker-compose.yaml`을 scratchpad에 받는다.
  - 아래만 남기고 줄인다.
    - **남길 서비스:** postgres(→`airflow-db`, `postgres:17.6`, 볼륨 `airflow-pgdata`, 비밀번호 `${AIRFLOW_DB_PASSWORD}`), airflow-init, apiserver, scheduler, dag-processor
    - **뺄 것:** redis·worker·triggerer·flower·airflow-cli
  - 바꿀 설정:
    - `AIRFLOW__CORE__EXECUTOR=LocalExecutor`
    - `AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Seoul`
    - `AIRFLOW__CORE__LOAD_EXAMPLES=False`
    - `AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True`
    - 관리 화면 포트 `127.0.0.1:8080:8080`(내 컴퓨터만)
    - 로그인: 로컬 전용이라 공식 파일의 기본 인증 방식을 그대로 쓰고, 계정은 airflow-init이 만든다.
  - `env_file: ../.env`를 둔다. 이 파일의 `DATABASE_URL`은 노트북용이라 컨테이너에서는 다음으로 덮어쓴다.
    - `DATABASE_URL=postgresql://career:${POSTGRES_PASSWORD}@host.docker.internal:5433/career`
    - `OPENAI_API_KEY: ${OPENAI_API_KEY}`
  - **GPU:** scheduler 서비스에 `deploy.resources.reservations.devices: [{driver: nvidia, count: all, capabilities: [gpu]}]`

- [ ] **Step 2: 이미지 만들기**
  - `FROM apache/airflow:3.3.2-python3.12`
  - root로 `libgl1 libglib2.0-0`을 설치한다(opencv용).
  - airflow 사용자로 `pip install -r requirements-airflow.txt`를 실행한다. `requirements-airflow.txt`는 이렇게 둔다.
    - `paddlepaddle-gpu==3.2.2`(`--extra-index-url https://www.paddlepaddle.org.cn/packages/stable/cu126/`)
    - `paddleocr==3.7.0`
    - `openai==2.7.2`
    - `psycopg[binary]==3.2.3`
    - `pillow==12.3.0`
    - `numpy==2.3.5`
    - `pytest==8.4.2`
  - 버전은 노트북 `requirements-paddle.txt`와 맞춘다.
  - Run: `docker compose -f airflow/docker-compose.yml build`
  - Expected: 빌드 성공

- [ ] **Step 3: 띄우고 확인**
  - Run: `docker compose -f airflow/docker-compose.yml up -d` 뒤 관리 화면 `http://localhost:8080` 응답(HTTP 200)
  - Run: `docker compose -f airflow/docker-compose.yml ps` → 4개 running(healthy), airflow-init은 exited 0

- [ ] **Step 4: GPU 확인 (실패하면 여기서 멈추고 사용자에게 알림)**
  - Run: `docker compose -f airflow/docker-compose.yml exec airflow-scheduler python -c "import paddle; print(paddle.device.cuda.device_count())"`
  - Expected: `1` 이상
  - **0이거나 오류면** CPU로 바꾸지 말고 오류 내용과 함께 사용자에게 알리고 멈춘다(스펙 결정).

- [ ] **Step 5: 컨테이너에서 서빙 DB·Slack·시험 확인**
  - Run: `docker compose -f airflow/docker-compose.yml exec airflow-scheduler python -c "import db_load; c=db_load.connect(); print(c.execute('select count(*) from job.posting').fetchone())"`
  - Expected: `(20,)` 이상
  - Run: `docker compose -f airflow/docker-compose.yml exec airflow-scheduler python -m pytest /opt/airflow/job-skill/tests -q`
  - Expected: 모두 통과(DB 시험은 컨테이너 `DATABASE_URL`로 돈다)
  - Run: `docker stats --no-stream` → Airflow 묶음 메모리 합계가 3GB 아래(평소)

- [ ] **Step 6: 커밋** — `git add airflow/Dockerfile airflow/requirements-airflow.txt airflow/docker-compose.yml .env.example; git commit -m "feat: Airflow Docker 묶음(LocalExecutor, GPU, 서빙 DB 연결)"`

---

### Task 8: DAG 3개

**Files:**
- Create: `airflow/dags/job_skill_dags.py`, `tests/test_dags.py`

**Interfaces:**
- Consumes: `pipeline_tasks.*`, `notify.on_failure`, `notify.send/msg_result/msg_daily_cost`, `db_queries.*`, `recheck.detect_changes`
- Produces (공통 설정):
  - DAG id: `backfill_once`, `daily_collect`, `recheck_postings`
  - 공통 `default_args`: `retries=2`, `retry_delay=timedelta(minutes=5)`, `on_failure_callback=notify.on_failure`
  - 공통 DAG 설정: `max_active_runs=1`, `catchup=False`
  - `start_date`는 `pendulum.datetime(2026, 10, 28, tz="Asia/Seoul")`이고, ②만 `pendulum.datetime(2026, 10, 30, 12, tz="Asia/Seoul")`
- Produces (DAG별, 태스크와 순서는 그림과 같다):
  - `backfill_once`
    - 설정: `schedule=None`, params `max_new: int | None = None`
    - 순서: `collect_list >> fetch_raw >> image_processing[ocr_images >> filter_sections] >> extract_llm >> load_db >> notify_result`, `fetch_raw >> extract_llm`
    - 수집은 `include_pending=False`, 예산은 `BACKFILL_LIMIT`
  - `daily_collect`
    - 설정: `schedule="0 0 * * *"`, `is_paused_upon_creation=True`, params `max_new`
    - 순서: `notify_cost`(다른 태스크와 연결 없음), `collect_list >> fetch_raw >> image_processing[...] >> extract_llm >> load_db >> notify_result`, `fetch_raw >> extract_llm`
    - 수집은 `include_pending=True`
    - 예산은 `budget_left(conn, DAILY_LIMIT, 오늘 KST)`
    - `notify_cost`는 어제(KST) `day_cost`로 `msg_daily_cost`
  - `recheck_postings`
    - 설정: `schedule=timedelta(days=3)`, `is_paused_upon_creation=True`
    - 순서: `list_open_postings >> detect_changes >> [close_postings, fetch_raw]`, `fetch_raw >> image_processing[...] >> extract_llm >> load_db >> notify_result`, `fetch_raw >> extract_llm`, `close_postings >> notify_result`
    - `list_open_postings`는 `open_postings` 결과를 `<run_dir>/open.json`에 쓴다.
    - `detect_changes`는 그 파일로 `recheck.detect_changes`를 실행하고, unchanged·changed에 `touch_checked`를 한다.
    - `close_postings`는 `changes.json`의 closed로 `mark_closed`를 한다.
    - 예산은 `budget_left(conn, DAILY_LIMIT, 오늘 KST)`
  - **실행 폴더:** 각 태스크는 `pipeline_tasks.run_dir_for(dag_id, run_id)`로 같은 폴더를 쓴다. 태스크 사이에는 파일로 넘기고, XCom에는 작은 숫자만 넣는다.
  - **결과 알림** `notify_result`: `msg_result(라벨, summary + 추가 숫자)`
    - 라벨: ③ "전체 수집", ① "매일 수집"(+ `"오늘 비용"`), ② "수정 확인"(+ `"확인"`, `"바뀜"`, `"마감"`, `"오늘 비용"`)

- [ ] **Step 1: 실패하는 시험 작성 — `tests/test_dags.py`** (컨테이너 안에서 실행)
  - `test_no_import_errors`: `DagBag(dag_folder="/opt/airflow/dags", include_examples=False).import_errors == {}`
  - `test_dag_ids_and_schedules`: 세 DAG가 있다.
    - `backfill_once.schedule is None`
    - `daily_collect`의 cron이 `"0 0 * * *"`
    - `recheck_postings`의 간격이 3일
    - 세 DAG 모두 `timezone.name == "Asia/Seoul"`, `max_active_runs == 1`
  - `test_daily_task_graph`:
    - `notify_cost`는 앞뒤 연결이 없다.
    - `collect_list`의 바로 다음은 `{fetch_raw}`이다.
    - `extract_llm`의 바로 앞은 `{fetch_raw, image_processing.filter_sections}`이다.
    - `close_postings` 태스크가 **없다**.
  - `test_recheck_task_graph`: `detect_changes`의 바로 다음이 `{close_postings, fetch_raw}`, `notify_result`의 바로 앞이 `{load_db, close_postings}`
  - `test_all_tasks_retry_and_alert`: 모든 태스크가 `retries == 2`이고 `on_failure_callback`에 `notify.on_failure`가 있다.

- [ ] **Step 2: 실패 확인**
  - Run: `docker compose -f airflow/docker-compose.yml exec airflow-scheduler python -m pytest /opt/airflow/job-skill/tests/test_dags.py -v`
  - Expected: FAIL (DAG 파일 없음)
- [ ] **Step 3: 구현** — Airflow 3 TaskFlow(`from airflow.sdk import dag, task, task_group`)
- [ ] **Step 4: 통과 확인** — 같은 명령 → 5 passed, 관리 화면에 DAG 3개가 **꺼진 상태**로 보인다.
- [ ] **Step 5: 커밋** — `git add airflow/dags tests/test_dags.py; git commit -m "feat: DAG 3개(일회성 전체 수집·매일 수집·수정 확인)"`

---

### Task 9: 작은 실제 실행 확인 + 문서

**Files:**
- Modify: `README.md` — "Airflow로 돌리기" 칸
  - 띄우는 명령 두 개(서빙 DB / Airflow)
  - `localhost:8080`
  - ③ 실행 → ①·② 켜기 순서
  - Slack 채널, 비용 상한
- Modify: `docs/superpowers/specs/2026-10-27-airflow-dags-design.md` — 만들면서 바뀐 점이 있으면 반영

- [ ] **Step 1: 비용 확인 받기 (유료)**
  - 사용자에게 알리고 **확인을 받은 뒤** 진행한다: "③을 `max_new=3`으로 돌리면 사람인 요청 약 10~20번, LLM 약 $0.02"

- [ ] **Step 2: ③ 작게 실행**
  - 관리 화면에서 `backfill_once`를 params `{"max_new": 3}`로 실행한다.
  - Expected:
    - 모든 태스크 초록
    - Slack `#data-pipeline`에 "✅ 전체 수집 완료 · 새 공고 3 · …"
    - `job.posting`이 3건 늘고, 새 `extraction_run`의 `raw_hash`·`llm_output_raw`가 채워져 있다.

- [ ] **Step 3: ① 바로 실행 → 멱등 확인**
  - `daily_collect`를 수동 실행한다(params `{"max_new": 3}`).
  - Expected:
    - 목록 맨 앞이 이미 아는 공고면 "새 공고 0"이 나온다.
    - 사이에 새로 올라온 공고가 있으면 그 수만큼만 나온다.
    - 어느 쪽이든 `job.posting`에 같은 공고번호가 두 번 들어가지 않는다(`UNIQUE`).
  - 로그에 "연속 5개 아는 공고 → 멈춤"이 나온다.

- [ ] **Step 4: 실패 알림 확인**
  - `step_load`가 잠깐 잘못된 `DATABASE_URL`을 쓰게 해 실패시킨다(환경변수만 바꾸고 코드는 그대로).
  - Expected: 재시도 2번 뒤 Slack에 "❌ daily_collect · load_db 실패 (3번째 시도) · …"
  - 확인 후 되돌린다.

- [ ] **Step 5: 문서 갱신 후 커밋하고, 사용자에게 결과 보고**
  - `git commit -m "docs: Airflow 운영 방법"`
  - ③ 전체 실행(약 $6)과 ①·② 켜기는 **사용자가 직접** 한다.
