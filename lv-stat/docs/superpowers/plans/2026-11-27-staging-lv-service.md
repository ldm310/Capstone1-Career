# 스테이징 LV 서비스 첫 판 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스테이징 사이트에서 로그인한 사람이 GitHub 계정 주소를 넣으면, 서버가 그 계정의 공개 코드를 분석하고 공고 상세의 레이더 차트에 공고마다 LV를 보여 준다.

**Architecture:** 웹(Next.js)이 `<CAREER_DATA_DIR>/lv-stat/jobs/`에 요청 파일을 만들고, 같은 EC2의 Python 작업자(systemd, 스테이징 전용)가 2단계 규칙 코드로 분석해 `profiles/`에 카테고리 LV를 쓴다. 공고 화면의 `/api/jobs/my-levels`는 프로필이 있으면 그 공고 문장 분류로 문장 점수를 그 자리에서 계산해 기존 모양으로 돌려준다(DB에 쓰지 않음). 작업자는 develop push 때 CD의 새 잡이 설치한다.

**Tech Stack:** Python 3.10+ 표준 라이브러리 + git(작업자, 시험은 unittest), Next.js 16/TypeScript(웹, 시험은 Playwright — 서버 논리는 `playwright.contract.config.ts`에 넣는 계약 시험, 화면은 e2e), GitHub Actions + systemd(배포).

**Spec:** [lv-stat/CLAUDE.md](../../../CLAUDE.md)의 '스테이징 LV 서비스'(2026-11-27 사용자 결정)와 [lv-stat/service/CONTRACT.md](../../../service/CONTRACT.md)(파일 형식·문장 점수 규칙). 실행자는 둘 다 읽는다.

## Global Constraints

- 시험 먼저(superpowers:test-driven-development): 실패하는 시험을 쓰고, 실패를 확인하고, 그다음에 코드를 쓴다.
- 분석 규칙은 `lv-stat/service/s2/`의 2단계 코드(cat_*·backend_gate·s2lib·s2_index 사본)를 그대로 쓴다. 고치는 곳은 Task 2·2b에 적은 것뿐이다. 화면 표시 '2단계 규칙'.
- LLM 보충 끔. 확인 못 한 항목은 '모름 n개'.
- 임계치(1~5단계 시작값): 커밋 1/7/30/180/365 · 바꾼 줄 1/200/1000/5000/25000 · 기간(일) 1/7/30/150/300 · 배포 레포 1/2/3/5/8 · 배포 기간 1/7/50/150/250 · DAG 1/2/5/10/20 · 데이터 엔지니어 기간 1/7/30/100/250 · 설계 테이블 1/3/8/20/50 · DB 기간 1/7/30/120/250 · API 연동 1/3/10/30/100 · 데이터 송수신 1/3/10/30/100 · 이벤트 1/10/30/100/300. AI: 연동 1/2/4/8/15 · 기능 1/2/3/5/8 · 기법 LLM 1/2/3/5/7 · 기법 ML 1/2/3/4/6(따로 단계로 바꿔 높은 쪽).
- 단계 평균은 소수 첫째 자리 ROUND_HALF_UP, 모름(None)은 평균에서 뺀다. DB 깊이는 근거 1곳이면 그 단계. 가점 없음.
- 문장 점수: CONTRACT.md 그대로(L·B·D·E·O·F·A만, lv null은 뺌, L은 문장에 적힌 언어 중 최고 LV·안 쓴 언어 0·없으면 최고 언어, 평균×20 반올림 0~100, 남는 것 없으면 점수 없음).
- 화면 라벨: `2단계 규칙 · LLM 보충 끔 · 제안 기준 · 본인 확인 안 됨`. 파란 선(비교 값) 숨김. UI 글은 짧은 한국어.
- 「Claude 임시값」(코드 주석에 표시): 레포 40개, 분석 20분, 전체 대기 20건, 사용자당 진행 중 1건, 400MB 넘는 레포는 `--filter=blob:none`, 커밋 검색 3쪽.
- Python 3.10에서 돌아야 한다. 받은 레포의 코드는 실행하지 않는다(git 명령만).
- 비밀값·공고 글·지인 계정/레포 이름은 파일·시험·커밋에 넣지 않는다(시험은 합성 문장·합성 레포). `.env`는 열지 않는다. 토큰은 환경 변수 `LV_GITHUB_TOKEN`으로만 받고 찍지 않으며, git 자식 프로세스에 넘기지 않는다.
- 운영(main, 3000번)은 건드리지 않는다. `frontend/` 수정은 이 기능에 필요한 곳만.
- 경로: 작업자 코드 `lv-stat/service/`, 웹 서버 논리 `frontend/lib/server/lv-stat.ts`, 순수 논리 `frontend/lib/lv-stat/`.

## Review Focus

1. 레포가 많거나 큰 계정이 20분 상한에 닿음: 멈추지 않고 받은 만큼으로 끝내며 `repos.notes`에 '시간 상한' 메모를 남겨야 한다. → Task 4 `test_deadline_stops_cloning_with_note`.
2. 토큰 없이 GitHub 호출 한도: 요청이 `failed`로 끝나고 "GitHub 호출 한도에 걸렸습니다(N분 뒤 다시 시도)"가 보여야 한다. → Task 1 `test_rate_limit_raises_with_wait`, Task 5 `test_rate_limited_job_fails_with_message`.
3. 분석 중 작업자 재시작: 그 요청은 '다시 요청해 주세요'로 닫히고 같은 사람이 바로 다시 요청할 수 있어야 한다. → Task 5 `test_recover_closes_running`, Task 8 `rejects second active job` 다음 `allows new job after failure`.
4. 코드 품질·보안·임베디드만 있는 문장, 분류 버전이 다른 공고: 점수 없이 빠지고 남은 축이 3개 미만이면 기존처럼 숫자만. → Task 7 `Q-only sentence has no score`, Task 10 `version mismatch returns no rows`.
5. 남의 결과: 웹은 로그인한 본인(namespace+subject) 프로필만 읽고, 클라이언트가 준 id로 파일 경로를 만들지 않는다. → Task 8 `profile path ignores client input`, `job id must be uuid`.

---

## 파트 A — 분석 작업자 (Python, `lv-stat/service/`)

### Task 1: GitHub API 읽기 부품

**Files:**
- Create: `lv-stat/service/s2/ghapi.py`
- Test: `lv-stat/service/tests/test_ghapi.py`

**Interfaces:**
- Produces: `request(path: str, timeout=30) -> tuple[object, dict]`, `get(path, default=None)`, `get_all(path, max_pages=10) -> list`(Link `rel="next"` 따라감, search 응답은 `items`), `q(s) -> str`(URL 인코딩), 예외 `NotFound`(404·409·451), `RateLimited(reset_epoch)`(429, 또는 403 + `X-RateLimit-Remaining: 0`; 메시지 `GitHub 호출 한도에 걸렸습니다(N분 뒤 다시 시도)`). 5xx·연결 오류는 3번까지 다시. 헤더: `Accept: application/vnd.github+json`, `User-Agent: lv-stat-worker`, 토큰 있으면 `Authorization: Bearer`. 시험용 환경 변수: `LV_GITHUB_API`(기본 `https://api.github.com`), `LV_GITHUB_OFFLINE=1`(모든 호출 `NotFound`).

- [ ] **Step 1: 실패하는 시험** — 표준 `http.server`로 가짜 API를 `127.0.0.1` 빈 포트에 띄우고 `LV_GITHUB_API`를 그 주소로 둔다.
  - `test_get_all_follows_next_link`: 1쪽이 `Link: <…?page=2>; rel="next"`, 2쪽이 마지막 → 두 쪽 항목이 순서대로 합쳐짐.
  - `test_search_items_unwrapped`: `{"items":[…]}` → 리스트.
  - `test_not_found_returns_default`: 404 → `get(...)`가 `None`, `get_all` → `[]`.
  - `test_rate_limit_raises_with_wait`: 403 + `X-RateLimit-Remaining: 0` + `X-RateLimit-Reset`(지금+120초) → `RateLimited`, 메시지에 `2분` 또는 `3분`.
  - `test_token_header_only_when_set`: `LV_GITHUB_TOKEN=abc` → 서버가 받은 `Authorization == "Bearer abc"`, 없으면 헤더 없음.
  - `test_offline_switch`: `LV_GITHUB_OFFLINE=1` → 서버 호출 0번, `get_all == []`.
- [ ] **Step 2:** `python3 -m unittest lv-stat/service/tests/test_ghapi.py -v` → FAIL(모듈 없음)
- [ ] **Step 3:** 구현(`urllib.request`, 표준 라이브러리만).
- [ ] **Step 4:** 같은 명령 → PASS. Python 3.10에서도: `$(uv python find 3.10) -m unittest …`
- [ ] **Step 5:** commit `feat(lv-stat): GitHub API 읽기 부품(gh CLI 대신)`

### Task 2: 2단계 코드를 작업 폴더·토큰 규칙에 맞추기

**Files:**
- Modify: `lv-stat/service/s2/s2lib.py`(경로 상수, `GENV`, `git()`), `lv-stat/service/s2/s2_index.py`(gh 호출 두 곳)
- Test: `lv-stat/service/tests/test_s2_port.py`

**Interfaces:**
- Consumes: Task 1 `get_all`, `q`.
- Produces (s2lib): `CODE`(코드 폴더), `S2 = os.environ.get('LV_S2_HOME') or CODE`, `INDEX`/`OUT`/`EMPTY_HOME`은 `S2` 아래, `LINGUIST = CODE/data/linguist/languages.yml`, `GENV`에서 `LV_GITHUB_TOKEN GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN ANTHROPIC_API_KEY`를 뺌, `LAZY_MARK = 'lv-allow-lazy'`(레포의 `.git/lv-allow-lazy`가 있으면 그 레포의 `git()`만 `GIT_NO_LAZY_FETCH`를 빼고 부름). s2_index: `api_shas(path) -> list[str]`, `api_prs(path) -> list[dict]`(필드: number, title, body[:4000], merged_at, merge_commit_sha, user, head_sha, created_at, labels).

- [ ] **Step 1: 실패하는 시험**
  - `test_paths_follow_home`: 하위 프로세스로 `LV_S2_HOME=<tmp>`를 주고 `s2lib.INDEX`·`OUT`이 `<tmp>` 아래, `LINGUIST`가 코드 폴더 아래 실제 파일.
  - `test_genv_has_no_tokens`: 하위 프로세스에 `LV_GITHUB_TOKEN=x`, `ANTHROPIC_API_KEY=y`를 주고 `s2lib.GENV`에 둘 다 없음.
  - `test_lazy_marker_per_repo`: 표시 파일이 있는 레포만 `GIT_NO_LAZY_FETCH`가 빠진 환경을 씀.
  - `test_index_offline_noreply_is_own`: 합성 레포(작성자 `123+tester@users.noreply.github.com` 커밋 3개, 남의 이메일 커밋 1개) + `people.json`(pid P01, login tester) → `LV_GITHUB_OFFLINE=1`로 `s2_index.py P01` 실행 → 색인의 내 커밋 3개, `person.json` 생김, `gh` 실행 0번(PATH에 가짜 `gh`를 두고 호출되면 실패).
- [ ] **Step 2:** 실행 → FAIL
- [ ] **Step 3:** 구현. 두 파일의 머리 설명에 '2단계 스파이크를 스테이징 서비스로 옮김(2026-11-27)'을 적는다. 그 밖의 줄은 바꾸지 않는다.
- [ ] **Step 4:** PASS(3.10 포함)
- [ ] **Step 5:** commit `feat(lv-stat): 2단계 코드를 작업 폴더·토큰 규칙에 맞춤`

### Task 2b: 큰 레포 부분 받기와 Linguist 자료(추가, 2026-11-28)

Task 2 검토에서 나온 두 가지를 고친다. ① Linguist 자료(`lv-stat/service/s2/data/linguist/`)가 `lv-stat/.gitignore`의 `data/`에 걸려 git에 없다. 그래서 CI와 배포된 작업자에서는 모든 색인이 실패한다. ② Task 2의 `lv-allow-lazy` 표시는 그 레포의 모든 git 호출에 lazy fetch를 켠다. 그래서 큰 레포를 색인하면 모든 작성자의 내용을 커밋마다 받으러 간다. 사용자 결정(2026-11-26: 400MB 넘는 레포는 빼지 않고 blob:none으로 받은 뒤 내 커밋이 바꾼 파일만 받는다)과 설계 7.2(내 커밋이 바꾼 경로의 blob, 분석 끝의 판과 그 경로의 이력만)에 맞춘다.

**Files:**
- Modify: `lv-stat/.gitignore`(`data/` 바로 다음 줄에 `!service/s2/data/`), `lv-stat/service/s2/s2lib.py`(표시), `lv-stat/service/s2/s2_index.py`(표시한 레포)
- git에 더함(내용은 그대로): `lv-stat/service/s2/data/linguist/`의 파일 5개(languages.yml·vendor.yml·documentation.yml·LICENSE·README.md)
- Test: `lv-stat/service/tests/test_s2_partial.py`(새 파일), `lv-stat/service/tests/test_s2_port.py`(`test_lazy_marker_per_repo`를 아래 `test_marker_never_enables_lazy`로 바꿈)

**Interfaces:**
- Produces (s2lib): `PARTIAL_MARK = 'lv-partial'`(`LAZY_MARK`를 대신함), `is_partial(d) -> bool`(`<d>/.git/lv-partial`이 있으면 참). `git()`은 표시와 관계없이 늘 `GENV`(`GIT_NO_LAZY_FETCH=1`)를 쓴다. git()이 lazy fetch를 켜는 길은 없다.
- Produces (s2_index), 표시한 레포에서만(표시 없는 레포는 지금 동작 그대로):
  - `prefetch_mine(d, refs, own, login) -> dict`: `{"paths": [...정렬], "blobs": n, "fetched": bool}`.
    1. `git log --no-merges --raw --no-abbrev -M --format=%x1e%H%x1f%ae <refs>` 한 번(트리만 읽고 내용은 읽지 않음). 내 커밋 = `sha in own` 또는 commits_of와 같은 noreply 정규식.
    2. 내 경로 = 내 커밋이 바꾼 경로(이름 바꿈은 양쪽 다). 그다음, 어느 작성자의 이름 바꿈이든 새 경로가 내 경로면 옛 경로를 더한다. 더 늘지 않을 때까지 한다(blame이 이름 바꾸기 전 판까지 따라가므로).
    3. 모든 커밋에서 경로(이름 바꿈은 어느 쪽이든)가 내 경로인 항목의 옛·새 blob id를 모은다(0만 있는 id와 중복은 뺌).
    4. 한 번에 받는다: `git -c fetch.negotiationAlgorithm=noop -c maintenance.auto=false -c gc.auto=0 fetch origin --no-tags --no-write-fetch-head --recurse-submodules=no --filter=blob:none --stdin`(표준 입력에 id 한 줄씩, 환경 GENV, timeout 900). 받을 id가 없으면 부르지 않는다(fetched 참). 실패하면 `fetched: false`로 두고 계속한다.
  - `commits_of`(표시한 레포): 커밋 정보는 `git log --no-merges --format=<지금과 같은 형식> <refs>`(diff 없이)로 모든 커밋을 받는다. 파일 항목은 `git --literal-pathspecs log --no-merges --numstat --format=%x1e%H <refs> --stdin`에 표준 입력 `--` 줄과 내 경로(한 줄에 하나)를 줘서 내 경로만 받는다. 내 경로를 건드리지 않은 커밋은 `files == []`다. 이 numstat이 실패하면 모든 커밋의 files를 []로 두고 `partial.numstat_ok = false`. `git_lazy`는 부르지 않는다. PR 번호 찾기는 지금과 같다.
  - `ensure_ref`(표시한 레포): 받기 필터를 `--filter=blob:none`으로 쓴다.
  - 색인 레코드에 `partial: {paths, blobs, fetched, numstat_ok}`를 더한다(표시 없는 레포에는 이 칸이 없음).
- Consumed by Task 4: 400MB 넘는 레포의 clone은 `--filter=blob:none`으로 받은 뒤 `.git/lv-partial`을 만든다.

- [ ] **Step 1: 실패하는 시험** — 합성 원격(`uploadpack.allowFilter=true`, `uploadpack.allowAnySHA1InWant=true`)을 `file://`로 `--filter=blob:none --no-checkout` clone하고 `.git/lv-partial`을 만든다(시험 준비에서 clone이 정말 부분 clone인지, 즉 남의 blob이 없는지 먼저 확인). 내 커밋은 noreply 이메일, `LV_GITHUB_OFFLINE=1`. 원격에는 내가 두 번 고친 `a.py`, 남이 만들고 남만 고친 `b.py`(판 3개)·`c.txt`, 남이 만든 `x.py`를 남이 `y.py`로 이름 바꾸고 그 뒤 내가 고친 경로를 둔다.
  - `test_partial_fetches_only_my_paths`: 색인 뒤 `a.py`·`x.py`·`y.py`의 모든 판 blob은 있고, `b.py`·`c.txt`의 blob은 없다(`GIT_NO_LAZY_FETCH=1 git cat-file -e`). `partial.paths == ['a.py', 'x.py', 'y.py']`, `fetched` 참.
  - `test_partial_numstat_mine_exact`: 내 커밋의 add/dele가 합성 내용대로이고, `b.py`·`c.txt`만 건드린 남의 커밋은 `files == []`, 모든 커밋(남의 것 포함)이 commits에 있다.
  - `test_partial_blame_my_lines`: `a.py`의 `my_lines`가 합성 내용대로.
  - `test_partial_one_fetch_no_lazy`: `GIT_TRACE2_EVENT`로 모은 git 실행 중 `cmd_name`이 fetch인 것은 1번뿐이다(lazy fetch 없음).
  - `test_partial_fetch_failure_continues`: clone 뒤 원격 폴더를 지우면 색인 파일과 `person.json`이 생기고 `partial.fetched` 거짓, 모든 커밋 정보는 있음.
  - `test_marker_never_enables_lazy`: 표시가 있는 레포도 git()이 받은 환경에 `GIT_NO_LAZY_FETCH=1`이 있고, `is_partial`은 표시한 레포에서만 참.
- [ ] **Step 2:** 실행 → FAIL
- [ ] **Step 3:** 구현. `.gitignore`를 고치고 Linguist 파일 5개를 git에 더한다(내용은 바꾸지 않음). 표시 없는 레포의 동작과 2단계 추출 규칙은 바꾸지 않는다. 두 파일의 머리 설명(lazy 설명)을 새 규칙에 맞춘다.
- [ ] **Step 4:** PASS(3.10 포함). 그다음 `git archive HEAD lv-stat/service`를 scratch에 풀어 거기서 같은 시험을 3.10으로 돌려 PASS(자료가 git에 들어갔는지 확인).
- [ ] **Step 5:** commit `fix(lv-stat): 큰 레포는 내 경로만 받고 Linguist 자료를 git에 넣음`

### Task 3: LLM 없는 마무리와 계산

**Files:**
- Create: `lv-stat/service/s2/s2_final.py`, `lv-stat/service/s2/calc.py`
- Test: `lv-stat/service/tests/test_calc.py`

**Interfaces:**
- Produces: `s2_final.py P01` → 카테고리마다 `out/P01/final-<cat>.json`(모듈 `finalize(person, data, {})`; `trace == 'no_trace'` 대상은 목록에서 뺌; 모듈이 실패하면 `finalize_error`를 넣고 계속). `calc.calc_person(pid) -> dict`(키 `L O B E D F A`, 값은 CONTRACT.md의 categories 칸 + B는 `note`). 상수 `FIXED`, `SPEC`, 함수 `stage(v, starts)`, `r1(x)`, `mean_known(xs)`.
- 계산 규칙: L = 언어마다 커밋·바꾼 줄·기간 단계 평균, `best`는 가장 높은 언어(같으면 먼저 나온 언어), 언어가 하나도 없고 prog 파일이 있으면 0.0. O = 배포 레포·기간. E = DAG·기간. D = 깊이(`database.depth` 값) + 테이블 + 기간. F = API·송수신·이벤트. A = 연동·기법(max(LLM 단계, ML 단계))·기능. B = 게이트(`backend.gate`) 0이면 0.0(`note` '백엔드 게이트 통과 레포 없음'), 아니면 login·was·api·log·D 깊이·O LV 평균. `unknown` = 그 카테고리에서 단계가 None인 수(B는 + 상태가 대기·모름이고 값이 없는 SEC/WAS/API/LOG 항목 수). 변수 읽기는 `variables[vid]`; `state`가 없고 `value`가 있으면 규칙 값.

- [ ] **Step 1: 실패하는 시험** — 합성 `final-*.json`을 `LV_S2_HOME/out/P01/`에 써서:
  - `test_spec_example_programming_33`: `prog.commits:Java` 120, `prog.lines:Java` 8000, `prog.period:Java` 90 → L lv 3.3, languages `{"Java": 3.3}`, best Java.
  - `test_best_language_and_per_language`: Java 3.3, Python 2.0 → best Java, 두 언어 다 있음.
  - `test_db_depth_single_evidence`: depth 4, 테이블 8(→3), 기간 30(→3) → D 3.3.
  - `test_backend_gate_zero_is_zero`: gate 0 → B 0.0, note.
  - `test_backend_mean_six`: gate 1, login 3·was 2·api 4·log 1, depth 4, 배포 레포 2(→2)·기간 50(→3) → O 2.5, B r1(mean(3,2,4,1,4,2.5)) = 2.8.
  - `test_unknown_counted_and_excluded`: F api 10(→3), data_io None, events 30(→3) → F 3.0, unknown 1.
  - `test_ai_techniques_max_of_llm_ml`: LLM 3(→3), ML 2(→2) → 기법 단계 3.
  - `test_final_drops_no_trace_and_survives_module_error`: no_trace 대상 1 + 흔적 대상 1인 vars → final에 흔적 대상만, `s5_policy.pending == 1`; 고장 난 가짜 모듈은 `finalize_error`.
- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS(3.10 포함)
- [ ] **Step 5(맞춤 점검, 커밋 안 함):** scratchpad의 2단계 20명 자료로 `calc_person`과 2단계 고정 사다리 결과(`calc-fixed12.json`·`calc-fixed-holdout.json`, DB는 `lv_any_evidence`)를 비교 → 차이는 DB 깊이 규칙이 다른 백엔드 칸뿐이어야 한다. 결과를 보고서에 적는다.
- [ ] **Step 6:** commit `feat(lv-stat): LLM 없는 마무리와 확정 사다리 계산`

### Task 4: 계정 하나 분석

**Files:**
- Create: `lv-stat/service/analyze.py`
- Test: `lv-stat/service/tests/test_analyze.py`

**Interfaces:**
- Consumes: Task 1(`get`, `get_all`, `request`, `q`, `RateLimited`, `NotFound`), Task 2, Task 3(`calc_person`).
- Produces: `METHOD = 'lv-stat-s2-20261127'`, `LABELS = ['2단계 규칙', 'LLM 보충 끔', '제안 기준', '본인 확인 안 됨']`, `EXTRACTORS = ['cat_prog_deploy', 'cat_backend_a', 'cat_backend_b', 'cat_db', 'cat_de', 'cat_fe', 'cat_ai']`, `class UserError(RuntimeError)`, `now_iso() -> str`, `discover(login, notes) -> (str, list[dict])`, `clone(full_name, dest, big, timeout) -> bool`, `run_step(script, home, timeout) -> (bool, str)`, `analyze(job, work_root, deadline, progress, clone_fn=clone) -> dict`(프로필, CONTRACT.md). `progress(stage: str, done: int|None, total: int|None)`.
- discover: `users/{login}`이 없으면 `UserError('GitHub 계정을 찾을 수 없습니다. 주소를 확인해 주세요.')`, `type != 'User'`면 `UserError('개인 GitHub 계정 주소를 넣어 주세요(조직 계정은 분석하지 않습니다).')`. 정식 login은 응답의 `login`. 본인 소유(`users/{login}/repos?type=owner&sort=pushed&per_page=100`, 3쪽)에서 private·fork 뺌(포크 수는 notes에), 커밋 검색(`search/commits?q=author:{login}&sort=committer-date&order=desc&per_page=100`, 3쪽; 한도에 걸리면 notes에 남기고 계속)으로 찾은 남의 공개·포크 아닌 레포는 `repos/{full}`로 정보를 받음. `pushed_at` 최근 순, 40개 넘으면 자르고 notes. 본인 소유 레포는 `commits?author={login}&per_page=1&sha={기본 브랜치}`가 비면 뺌.
- analyze: 단계 이름 `레포 찾기 → 레포 받기(done/total) → 색인(done/total) → 규칙 적용(done/7) → 계산`. 레포가 없으면 `UserError('공개 레포에서 이 계정의 커밋을 찾지 못했습니다.')`, 하나도 못 받으면 `UserError('레포를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.')`. 남은 시간이 60초 아래면 더 받지 않고 notes `시간 상한에 닿아 레포 n개는 받지 못함`. 추출기 실패는 notes에 이름을 남기고 계속. 작업 폴더 `<work_root>/<job id>`는 끝나면(실패해도) 지운다. 프로필 `repos = {found, analyzed, failed, notes}`.
- clone: `git -c core.hooksPath=/dev/null -c protocol.file.allow=never clone --no-checkout --no-tags --quiet --filter=blob:limit=1m`(400MB 넘으면 `--filter=blob:none` + `.git/lv-partial`, Task 2b), 주소 `https://github.com/{full}.git`, 환경은 `s2lib.GENV`.
- people.json의 `prs`는 본인 소유·포크 아님·400MB 이하 레포만 참이다(2단계 범위). 남의 레포는 PR 목록을 받지 않는다(s2_index가 레포 전체 PR을 끝까지 받기 때문).
- 색인 결과 읽기: s2_index는 레포마다 실패를 `error`(repr)로 남기고 0으로 끝난다. 그래서 색인 뒤 `<home>/index/<pid>/*.json`을 읽는다. `error`가 `RateLimited(`로 시작하면 그 안의 메시지(`GitHub 호출 한도에 걸렸습니다(N분 뒤 다시 시도)`)로 `UserError`를 낸다. 그 밖의 error가 있는 레포는 `repos.failed`에 세고 notes `레포 n개는 색인하지 못함`을 남긴다. 표시한 레포의 `partial.fetched`가 거짓이면 notes `큰 레포 n개는 파일을 받지 못함`.
- run_step: 자식 프로세스를 새 세션(`start_new_session=True`)으로 띄우고, 시간을 넘기면 프로세스 묶음 전체를 끝낸다(`os.killpg`). 색인 단계가 시간을 넘기면 색인 파일이 있는 레포만으로 `person.json`(s2_index와 같은 칸: pid, login, role, level, repo_keys, index_s)을 쓰고 notes `시간 상한에 닿아 레포 n개는 색인하지 못함`을 남긴 뒤 계속한다.

- [ ] **Step 1: 실패하는 시험** — 가짜 API(Task 1과 같은 방식) + `clone_fn`은 합성 로컬 레포를 복사하는 함수:
  - `test_discover_filters_and_orders`: 소유 레포 3개(하나 fork, 하나 private), 검색 결과에 남의 레포 1개 + 포크 1개 → 결과 2개, pushed_at 최근 순, notes에 포크 1개.
  - `test_discover_org_rejected`, `test_discover_missing_user`.
  - `test_discover_caps_40_with_note`.
  - `test_analyze_end_to_end_synthetic`: 합성 Python 레포 1개 → 프로필 `schema == 'lv-stat-profile/1'`, `labels == LABELS`, categories 키 7개, L languages에 Python, L lv > 0, 모든 lv는 None 또는 0~5, 작업 폴더가 지워짐, progress가 다섯 단계 이름을 차례로 받음.
  - `test_deadline_stops_cloning_with_note`: deadline이 이미 지남 → 받지 않고 `UserError` 또는 notes에 '시간 상한'(레포 0이면 UserError).
  - `test_no_repos_user_error`.
  - `test_index_rate_limit_fails`: 가짜 API가 커밋 목록에 403 + `X-RateLimit-Remaining: 0` → `UserError`, 메시지가 `GitHub 호출 한도에 걸렸습니다(`로 시작.
  - `test_index_error_counted_as_failed`: 색인 error가 있는 레포 → `repos.failed == 1`, notes에 `색인하지 못함`.
  - `test_prs_only_owned_small`: people.json에서 남의 레포·400MB 넘는 레포의 `prs`가 거짓, 본인 소유 작은 레포는 참.
  - `test_big_repo_uses_partial`: 400MB 넘는 레포(`size > 400*1024`, KB)는 clone 인자에 `--filter=blob:none`이 있고 `.git/lv-partial`이 생긴다.
  - `test_index_timeout_keeps_indexed`: 색인 단계가 시간을 넘기면 색인된 레포만으로 계산하고 notes에 `시간 상한`.
- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS(3.10 포함)
- [ ] **Step 5:** commit `feat(lv-stat): GitHub 계정 하나 분석`

### Task 5: 작업자(요청 파일 처리)

**Files:**
- Create: `lv-stat/service/worker.py`
- Test: `lv-stat/service/tests/test_worker.py`

**Interfaces:**
- Consumes: Task 4 `analyze`, `UserError`, `now_iso`; Task 1 `RateLimited`.
- Produces: CLI `python3 -I worker.py --data-dir <dir> [--once] [--max-minutes 20] [--poll 5] [--self-check]`(배포 스크립트가 이미 이 모양을 쓴다). 함수 `profile_key(namespace, subject_id) -> str`(sha256 앞 32자), `write_json(path, data)`(같은 폴더 임시 파일 + `os.replace`), `read_json(path)`, `class Dirs(root)`(jobs·profiles·work 만듦), `valid_job(job)`, `list_jobs(dirs)`(파일 이름이 uuid v4 `.json`인 것만), `next_job(dirs)`(queued 중 createdAt 가장 이른 것), `recover(dirs)`(running → failed `작업자가 다시 시작되어 중단됐습니다. 다시 요청해 주세요.`, work 비움), `process(dirs, name, job, max_minutes, analyze_fn=None)`, `self_check(root) -> int`(Python ≥3.10, git, 데이터 폴더 쓰기, Linguist 자료(languages.yml·vendor.yml·documentation.yml이 있고 비어 있지 않음), 모든 .py 문법을 메모리에서 compile; 문제 없으면 `OK` 출력·0). 시작 로그에 토큰 유무만(`token yes/no`). login 규칙 `^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$`.
- 상태 전이: queued → running(`stage`, `progress`, `startedAt`) → done(`profileKey`, `finishedAt`) | failed(`error`): UserError·RateLimited는 그 메시지, 그 밖은 `분석 중 오류가 났습니다. 잠시 뒤 다시 시도해 주세요.`(자세한 것은 로그에만).

- [ ] **Step 1: 실패하는 시험** — 가짜 `analyze_fn` 사용:
  - `test_profile_key_matches_contract`, `test_next_job_takes_oldest_queued`, `test_ignores_non_uuid_names`, `test_recover_closes_running`, `test_invalid_login_fails`.
  - `test_process_success_writes_profile_and_key`: 프로필 파일 이름 = profile_key, 요청 `done`·`profileKey`.
  - `test_user_error_message_kept`, `test_rate_limited_job_fails_with_message`, `test_unexpected_error_generic_message`.
  - `test_progress_updates_job_file`: 가짜 analyze가 progress('색인', 1, 3) → 파일에 반영.
  - `test_self_check_ok`, `test_self_check_reports_bad_syntax`(임시 사본에 문법 오류 파일).
- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS(3.10 포함)
- [ ] **Step 5(실제 확인, 커밋 안 함):** 로컬에서 사용자 본인 계정 하나를 `--once`로 끝까지(토큰은 `gh auth token`을 환경 변수로만, 찍지 않음). 걸린 시간·레포 수·카테고리 LV를 보고서에 적는다.
- [ ] **Step 6:** commit `feat(lv-stat): 스테이징 분석 작업자`

### Task 6: 배포 스크립트 검토(이미 있음)

**Files:** `deploy/lv-stat/deploy_worker.sh`, `deploy/lv-stat/tests/test_deploy_worker.py`, `deploy/lv-stat/README.md`, `.github/workflows/cd.yml`(`lv_worker`, `staging-lv-worker`), `.github/workflows/ci.yml`(`lv_stat`, `lv-stat` 잡)

- [ ] 검토 에이전트가 읽고, 아래를 확인한다: develop이 아니면 거부, 토큰 값이 출력·명령행·자식 환경에 없음, 파일 600, 같은 sha 두 번은 재시작만, 실패 시 되돌림, 5판만 남김, CI 잡이 Python 3.10으로 `lv-stat/service/tests`·`pipeline/selftest.py`·배포 시험을 돎, main에서 `lv_worker`는 늘 false.
- [ ] `bash -n deploy/lv-stat/deploy_worker.sh && python3 -m unittest discover -s deploy/lv-stat/tests -v` → 13/13 PASS
- [ ] 작업자가 생긴 뒤: 배포 스크립트 시험이 실제 `worker.py --self-check`와도 맞는지(가짜 HOME) 한 번 돌린다.
- [ ] commit `feat(deploy): 스테이징 LV 작업자 배포 잡`

## 파트 B — 웹 (`frontend/`)

먼저 `frontend/AGENTS.md`대로 `node_modules/next/dist/docs/`의 route handler 안내를 읽는다. 새 서버 논리 시험은 `tests/lv-stat-contract.spec.ts` 하나에 모으고 `playwright.contract.config.ts`의 `testMatch`에 더한다(CI가 `npm run test:api-contract`로 돌린다). 실행: `cd frontend && npx playwright test --config=playwright.contract.config.ts tests/lv-stat-contract.spec.ts`.

### Task 7: 문장 점수 함수

**Files:**
- Create: `frontend/lib/lv-stat/score.ts`, `frontend/types/lv-stat.ts`
- Test: `frontend/tests/lv-stat-contract.spec.ts`(describe `score`)

**Interfaces:**
- Produces: 타입 `LvProfile`(CONTRACT.md profile 그대로), `LvCategoryCode = 'L'|'B'|'D'|'E'|'O'|'F'|'A'`, `LvJob`(CONTRACT.md job). 함수 `detectLanguages(text: string): string[]`(Linguist 이름, 사전은 「Claude 임시값」 주석), `scoreKeyword(profile: LvProfile, keyword: {text: string; categoryCodes: string[]}): {score: number | null; used: LvCategoryCode[]}`.
- [ ] **Step 1: 실패하는 시험**: `Java but not JavaScript`("Java/Spring 경험" → Java만, "JavaScript 경험" → JavaScript만), `Korean names`("자바 또는 파이썬" → Java, Python; "자바스크립트" → JavaScript만), `Go and C are case-sensitive words`("Go 언어" → Go, "go to market" → 없음, "C/C++" → C, C++; "C#" → C#만), `multi-category mean`(B 3.0, D 2.0, 문장 [B,D] → 50), `L uses named language`(Java 3.3·Python 2.0, "Python 개발" [L] → 40), `L named but unused language is 0`("Kotlin 개발" [L] → 0), `L without language uses best`([L] → 66), `Q-only sentence has no score`([Q] → null), `null lv category dropped`(D lv null, [B,D] → B만), `clamped integer 0..100`.
- [ ] **Step 2:** 실행 → FAIL → **Step 3:** 구현 → **Step 4:** PASS
- [ ] **Step 5:** commit `feat(frontend): LV 문장 점수 함수`

### Task 8: 요청·프로필 파일 저장소(서버)

**Files:**
- Create: `frontend/lib/server/lv-stat.ts`
- Test: `frontend/tests/lv-stat-contract.spec.ts`(describe `store`)

**Interfaces:**
- Consumes: Task 7 타입.
- Produces: `lvDataDir(): string`(`path.join(process.env.CAREER_DATA_DIR || path.join(process.cwd(), '.career-data'), 'lv-stat')`, store.ts의 `db()`와 같은 기준), `profileKey(namespace, subjectId): string`, `parseGithubLogin(input: string): string | null`(https만, 호스트 `github.com` 또는 `www.github.com`, 사용자·암호·포트·쿼리·조각 없음, 경로 `/<login>` 또는 `/<login>/<repo>`(끝 `/`·`.git` 허용), login 규칙은 Task 5와 같음), `createJob({namespace, subjectId, login, input}): Promise<LvJob>`(uuid v4, 같은 사람의 queued·running이 있으면 `LvStatError('이미 분석 중이에요. 끝나면 다시 시도해 주세요.', 409)`, 전체 queued가 20 이상이면 `LvStatError('지금 분석 요청이 많아요. 잠시 뒤 다시 시도해 주세요.', 503)`), `latestJob(namespace, subjectId): Promise<LvJob | null>`(그 사람의 가장 최근 createdAt), `readProfile(namespace, subjectId): Promise<LvProfile | null>`(파일이 없거나 깨지면 null, `schema`가 `lv-stat-profile/1`이 아니면 null), `class LvStatError(message, status)`. 파일 쓰기는 임시 파일 + rename, 폴더 0o700. 파일 이름은 서버가 만든 uuid·profileKey만 쓴다.
- [ ] **Step 1: 실패하는 시험**(임시 `CAREER_DATA_DIR`): `parseGithubLogin accepts account and repo URLs`, `rejects other hosts, credentials, ports, queries, bad logins`, `profileKey matches sha256 prefix`(Python 작업자와 같은 값: `staging:abc` → `hashlib` 결과를 시험에 상수로), `createJob writes queued job`, `rejects second active job`, `allows new job after failure`(작업자가 failed로 바꾼 뒤), `global queue cap 20`, `latestJob is per subject`, `readProfile ignores other subjects and bad schema`, `profile path ignores client input`, `job id must be uuid`.
- [ ] **Step 2:** FAIL → **Step 3:** 구현(`import "server-only"`) → **Step 4:** PASS
- [ ] **Step 5:** commit `feat(frontend): LV 분석 요청·프로필 파일 저장소`

### Task 9: 공고 문장 받기를 함수로 빼기

**Files:**
- Create: `frontend/lib/server/job-keywords.ts`
- Modify: `frontend/app/api/jobs/keywords/route.ts`(본문을 함수 호출로)
- Test: `frontend/tests/lv-stat-contract.spec.ts`(describe `job keywords`)

**Interfaces:**
- Produces: `jobKeywords(jobId: string): Promise<{status: number; body: JobKeywordsBody}>` — 지금 route가 돌려주는 모든 경우(EXAMPLE·UNAVAILABLE·SAVED_REVIEW·400·503·502)를 같은 상태 코드·본문으로. `JobKeywordsBody`는 `{source, version?, keywords: {id, text, requirementType?, categoryCodes, level}[], levelScoringEnabled} | {error}`.
- [ ] **Step 1: 실패하는 시험**(로컬 HTTP 가짜 백엔드, `backend-api-contract.spec.ts`와 같은 방식): `be:9001 returns classified keywords only`, `backend down → 502`, `no BACKEND_URL → 503`, `bad id → 400`, route GET과 `jobKeywords` 결과가 같음.
- [ ] **Step 2:** FAIL → **Step 3:** 옮기기(동작 바꾸지 않음) → **Step 4:** PASS + 기존 `npm run test:api-contract` 전체 PASS
- [ ] **Step 5:** commit `refactor(frontend): 공고 문장 받기를 함수로`

### Task 10: 프로필로 공고 LV 계산(my-levels)

**Files:**
- Modify: `frontend/types/posting-level.ts`(`source: "RDS" | "LV_STAT"`, 선택 칸 `labels?: string[]`, `identityVerified?: boolean`, `methodVersion?: string`), `frontend/app/api/jobs/my-levels/route.ts`
- Create: `frontend/lib/server/profile-levels.ts`
- Test: `frontend/tests/lv-stat-contract.spec.ts`(describe `profile levels`)

**Interfaces:**
- Consumes: Task 7 `scoreKeyword`, Task 8 `readProfile`, Task 9 `jobKeywords`, `profileNamespace()`(`lib/server/notices.ts`).
- Produces: `profilePostingLevels(subject: string, jobId: string, version: string): Promise<PostingLevels | null>` — 프로필 없으면 null. 있으면 `jobKeywords(jobId)`(200이 아니면 throw), 그 본문 `version !== version`이면 `levels: []`, 아니면 키워드마다 `scoreKeyword`, 점수 있는 것만 `{keywordId: id, text, categoryCodes, score, referenceScore: null, referenceKind: null, evaluationKind: 'CONFIRMED', evaluatedAt: profile.analyzedAt}`. `source: 'LV_STAT'`, `sources: [{id: 'lv-stat:' + profile.login, kind: 'GITHUB', title: profile.login, simulated: false}]`, `labels: profile.labels`, `identityVerified: false`, `methodVersion: profile.method`. route: 로그인 확인 뒤 `profilePostingLevels`를 먼저 부르고, null이면 지금처럼 `postingLevels`. 오류는 지금과 같은 502 글.
- [ ] **Step 1: 실패하는 시험**: `rows computed from profile`(가짜 백엔드 문장 3개: [B]·[L, Java 문장]·[Q] → 행 2개, 점수 CONTRACT대로), `rows match page matching rule`(keywordId·text·categoryCodes가 키워드와 같음), `version mismatch returns no rows`, `no profile returns null`, `labels and sources present`.
- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS, `npm run typecheck` PASS
- [ ] **Step 5:** commit `feat(frontend): 분석 프로필로 공고별 LV 계산`

### Task 11: 분석 요청 API

**Files:**
- Create: `frontend/app/api/lv-stat/analysis/route.ts`
- Test: e2e `frontend/tests/lv-stat-analysis.spec.ts`(dev 서버, 로그인은 기존 e2e 시험이 쓰는 방식을 따른다)

**Interfaces:**
- Consumes: Task 8 전부, `user`·`isGuest`·`originCheck`·`jsonBody`·`rateLimit`(`lib/server/store.ts`), `profileNamespace()`.
- Produces: `POST /api/lv-stat/analysis` 본문 `{url}` → 401(비로그인·손님), 403(출처), 429(rateLimit, 키 `lv-stat:` + id, 최대 6), 400 `GitHub 계정 주소를 넣어 주세요. 예: https://github.com/아이디`, 409/503(LvStatError), 202 `{job}`. `GET` → 401 또는 200 `{job: LvJob | null, profile: LvProfile | null}`(본인 것만). 헤더 `Cache-Control: private, no-store`. `runtime = "nodejs"`.
- [ ] **Step 1: 실패하는 시험**: 비로그인 POST·GET 401, 잘못된 주소 400, 로그인 후 POST 202 → GET에 같은 job, 두 번째 POST 409, 다른 사용자 GET에 남의 job 없음.
- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS
- [ ] **Step 5:** commit `feat(frontend): GitHub 계정 LV 분석 요청 API`

### Task 12: 분석 화면과 차트 표시

**Files:**
- Create: `frontend/components/analysis/github-lv-analysis.tsx`
- Modify: 분석 화면 페이지(`AnalysisFlow`를 그리는 page) — 기존 `AnalysisFlow` 위에 새 칸을 더한다(기존 흐름·`/api/analysis-preview`는 그대로), `frontend/components/jobs/saved-level-radar.tsx`(CONFIRMED + `labels`가 있으면 '(더미)' 대신 라벨 한 줄), 필요하면 CSS
- Test: e2e `frontend/tests/lv-stat-analysis.spec.ts`(API는 `page.route`로 흉내), 기존 `job-category-comparison.spec.ts`·`analysis-flow.spec.ts`가 계속 통과

**Interfaces:**
- Consumes: Task 11 API 모양, Task 10 `PostingLevels.labels`.
- 화면 글: 제목 `GitHub 계정으로 공고별 LV 보기`, 입력 placeholder `https://github.com/아이디`, 버튼 `분석 시작`, 안내 한 줄 `분석이 끝나면 공고 상세의 레이더 차트에 공고마다 LV가 나와요.`, 진행 `단계 이름 (done/total)`, 실패 `error` 그대로 + `다시 시도`, 끝 요약: 카테고리 7개 `이름 LV x.x`(null이면 `판정 불가`, unknown>0이면 `모름 n개`), 라벨 한 줄. 상태가 queued·running이면 5초마다 GET.
- [ ] **Step 1: 실패하는 시험**: 비로그인은 로그인 안내, 주소 넣고 시작 → 진행 표시 → (흉내 응답이 done) 요약에 7개 카테고리와 라벨, 실패 응답이면 오류 글과 다시 시도, 공고 화면에서 LV_STAT 응답이면 '(더미)' 없이 라벨이 보이고 파란 선이 없음.
- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS + 기존 두 spec PASS
- [ ] **Step 5:** `npm run lint`·`npm run typecheck`·`npm run test:api-contract`·`npm run build` 모두 PASS
- [ ] **Step 6:** commit `feat(frontend): GitHub 계정 LV 분석 화면`

## 파트 C — 합치기

### Task 13: 통합 확인·전체 검토·병합

- [ ] 로컬 통합: 임시 `CAREER_DATA_DIR`로 `next dev`를 띄우고, 작업자(`--once`)로 사용자 본인 계정을 분석한 프로필을 넣은 뒤 공고 화면 레이더를 스크린샷으로 확인(백엔드가 없으면 예시 공고 또는 가짜 백엔드).
- [ ] superpowers:requesting-code-review로 브랜치 전체 검토(작업자·웹·배포 각각) → 지적은 시험 먼저로 고침.
- [ ] 공개 레포 점검: 비밀값 모양·공고 글·지인 계정/레포 이름이 커밋할 파일에 없음(이름 목록은 scratchpad에서만 읽음).
- [ ] superpowers:verification-before-completion: `lv-stat/service/tests`(3.10)·`deploy/lv-stat/tests`·`pipeline/selftest.py`·`npm run lint`·`typecheck`·`test:api-contract`·`build` 결과를 다시 돌려 보고서에 붙인다.
- [ ] superpowers:finishing-a-development-branch: push `feature/lv-stat` → develop PR → CI 통과 → 병합 → CD 성공·`career-lv-worker-staging` active 확인 → 스테이징에서 시험 회원으로 로그인 → 본인 계정 분석 → 공고 화면 레이더 스크린샷 → 사용자에게 보고, 남은 문제는 CLAUDE.md 「미정」으로.

## 변경 기록 (2026-11-28, 작업 중 정한 것)

검토에서 나온 지적을 컨트롤러가 판정해 위 글과 다르게 만든 곳이다. 자세한 근거는 각 커밋 메시지와 [CONTRACT.md](../../../service/CONTRACT.md)에 있다.

- Task 2b: raw 읽기는 `-M` 대신 `-M100%`(그냥 `-M`은 내용을 읽어 blob:none에서 멈춤), 내 경로 numstat에 `--full-history`, 경로는 `-z`로 읽음, 합친 커밋에서만 생긴 내 경로의 판도 받음, gitlink는 받지 않음, 받은 뒤 부분 clone 설정(`remote.origin.promisor`·`partialclonefilter`·`extensions.partialClone`)을 지워 git 2.45 전 판에서도 더 받으러 가지 않음, blame 실패는 `partial.blame_failed`로 기록. 「제안」 내 경로가 생긴 커밋에서 지워진 파일의 판 하나씩도 받음(확인 전).
- Task 3: LLM 보충을 끈 판에서 LLM 확인을 기다리는 변수는 모름으로 센다(확인 0은 평균에서 뺌, 0보다 크면 확인된 만큼). 게이트가 대기라 0이면 B는 null(판정 불가). B 평균은 10진수로 반올림.
- Task 4: 시간 배분(「Claude 임시값」 받기 50%·색인 80%, 마무리 몫 4분을 뺀 시간 기준, 모든 단계가 상한 안에서 끝남), 색인 0개면 `레포를 색인하지 못했습니다. 잠시 뒤 다시 시도해 주세요.`, 반쯤 쓴 vars 파일은 지우고 메모, 규칙 단계가 시간 상한에 닿으면 메모 한 줄.
- Task 5: 같은 데이터 폴더에 작업자 하나(`.worker.lock`), 프로필을 쓴 뒤 요청을 done으로 바꿈, 자체 점검은 git 판을 찍지 않음(시작 로그에만), 요청 파일 쓰기에 실패한 요청은 건너뜀.
- Task 6: 되돌릴 때 작업자 로그를 CI 로그에 옮기지 않음, 자체 점검의 stdout만 CI 로그에 남김, 실수로 올린 `__pycache__`를 뺌(기록에서도 push 전에 지움).
- Task 8: `readProfile`은 CONTRACT 모양 전체와 그 사람의 것인지까지 확인.
- Task 9·10: 공고 문장·my-levels 실패를 서버 로그에 이름만 남김. 공고 LV 행에 `usedCodes`. 데모 계정은 프로필을 읽지 않음.
- Task 11: 데모 계정 POST는 403 `데모 계정은 GitHub 분석을 할 수 없어요.`, GET은 파일을 읽지 않고 null. 같은 규칙을 CI가 도는 계약 시험에도 둠.
- Task 12: 레이더는 `usedCodes ?? categoryCodes` 축에만 값을 놓음, 분석 결과 행은 '(더미)' 대신 라벨 한 줄.
