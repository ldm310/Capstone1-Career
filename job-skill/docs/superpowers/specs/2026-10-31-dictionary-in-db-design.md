# 표준화 사전을 DB로 — 설계

작성: 2026-10-31 · 대상 폴더: `job-skill/` · 브랜치: `feature/job-skill` 먼저, `feature/job-skill-aws`로 가져옴(cherry-pick, 지금까지 방식)

## 1. 왜 하나

표준화 사전(능력·기술·별칭·상위·스킬이 아닌 낱말)은 아직 완성본이 아니다. **서비스를 써 보면서 팀이 함께 다듬어 간다.**
지금은 사전의 원본이 저장소의 `capabilities.json`이고, DB의 사전 표는 `db_load.py sync-dict`로 한쪽으로 복사한 사본이다.
그래서 팀원이 DB에서 고쳐도 추출에 쓰이지 않고, 다음 `sync-dict` 때 덮어써진다.
→ **원본을 DB 하나로 바꾼다.** 팀원(BE)은 RDS에 SQL로 사전 표를 직접 고치고(관리 화면은 만들지 않음), 고친 내용은 다음 추출부터 반영된다.

## 2. 사용자가 정한 것

1. **사전의 원본은 DB.** `capabilities.json`은 지운다. 추출은 DB의 사전을 읽는다.
   - aws 브랜치는 RDS, 로컬 브랜치는 노트북 Docker DB(`career-db`)의 사전을 읽는다(각 브랜치가 원래 쓰는 DB).
2. **추출에서 사전을 쓰는 두 곳 모두 DB에서 읽는다.**
   - LLM 입력: 능력 목록(JSON 스키마의 `enum`)과 능력별 대표 기술 예시(`instructions()`)
   - 후처리(`capdict.py`): 기술 이름 통일, 상위 기술 연결, 스킬이 아닌 낱말 빼기, 능력 충족 판정
3. **이미 뽑아 둔 결과는 다시 맞추지 않는다.** 바뀐 사전은 다음 추출부터만 쓰인다.
4. **빈 DB를 채우는 SQL 하나는 Git 저장소에 둔다.** 테스트(pytest)·앞으로 만들 CI(GitHub Actions, PostgreSQL을 잠깐 띄워 씀)·새로 만드는 DB용.
   - **DB(RDS)에 있는 사전을 기준으로 만드는 명령**을 둔다. 필요할 때 다시 만들어 커밋한다.
   - 특히 12/20 뒤 RDS를 지우기 전에 반드시 내려받는다(안 하면 팀이 다듬은 사전이 사라짐) → README에 적는다.
5. **사전 변경 기록은 DB 안의 기록 표에 남긴다(트리거).** 누가(`dongmin`·`seonyoung`·파이프라인 `career`), 언제, 어느 표의 어느 줄을, 무엇에서 무엇으로 바꿨는지. 잘못 고친 것은 이 기록의 예전 값을 보고 되돌린다. (로그·CloudWatch는 쓰지 않음)
6. **새로 생기는 표(와 칸)는 논리 ERD(`docs/erd.svg`·`.png`)와 물리 ERD(`docs/erd-physical.svg`·`.png`) 그림, `docs/physical-design.md`에 모두 넣는다.**
7. 팀원 권한(2026-10-31 이미 RDS에 적용): 파이프라인 표는 읽기·FK만, **사전 표는 읽기·쓰기**, 팀원이 만든 표는 모두. 표는 모두 `public`.

## 3. 목표 / 하지 않는 것 / 실패로 보는 것

**목표**
- 팀원이 RDS에서 `UPDATE tech SET aliases = ...` 같은 SQL 한 줄로 사전을 고치면, 다음 날 매일 수집(①)의 추출부터 그 사전으로 뽑힌다.
- 사전을 누가 언제 무엇을 바꿨는지 SQL로 조회할 수 있다.
- 테스트는 RDS 없이 저장소만으로 돈다.

**하지 않는 것**
- 사전을 고치는 화면
- 이미 뽑은 결과를 새 사전으로 다시 맞추기(다시 표준화·다시 추출)
- 로컬 DB와 RDS 사전을 서로 맞추기(필요하면 내려받은 SQL로 사람이 채운다)

**실패로 보는 것** (내 추측 — 사용자에게 확인 안 함)
- 팀원의 SQL 실수 하나로 매일 수집이 멈추는 것
- 사전이 바뀌었는데 기록이 빠지는 것(어떤 경로로 고치든 남아야 함)
- 사전이 RDS와 함께 사라지는 것

## 4. 만드는 것

### 4-1. 새 표 2개와 칸 하나 (마이그레이션 `004`)

**스킬이 아닌 낱말 `exclude_word`** — 지금 `capabilities.json`의 `exclude`에만 있던 것을 옮긴다. *(이름·구조는 내 판단)*
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 낱말ID | `id` | bigint | PK, 자동 증가 |
| 낱말 | `word` | text | NOT NULL |
| 종류 | `kind` | text | NOT NULL, `LLM 모델`(이름 안에 들어 있으면 제외) / `기술 아님` / `일반 낱말`(낱말만 빼고 요건은 남김) |
| | | | UNIQUE(kind, word) |

지금 들어 있는 값: LLM 모델 16개, 기술 아님 34개, 일반 낱말 11개. 동작은 지금 `capdict.py`와 같다(대소문자·공백 무시).

**사전 변경 기록 `dictionary_change`** *(이름·구조는 내 판단)*
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 기록ID | `id` | bigint | PK, 자동 증가 |
| 바꾼 시각 | `changed_at` | timestamptz | NOT NULL, 기본값 now() |
| 바꾼 사람 | `changed_by` | text | NOT NULL, DB 접속 계정(`session_user` — 팀원은 접속 뒤 `team` 역할로 바뀌므로 `current_user`가 아님) |
| 표 | `table_name` | text | NOT NULL, `capability`/`tech`/`tech_capability`/`exclude_word` |
| 동작 | `action` | text | NOT NULL, `넣기`/`고치기`/`지우기` |
| 예전 값 | `old_row` | jsonb | 넣기면 비움 |
| 새 값 | `new_row` | jsonb | 지우기면 비움 |

- 위 4개 표에 `AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW` 트리거를 건다. 줄 전체를 jsonb로 남긴다.
- 값이 실제로 안 바뀐 `UPDATE`(예: `SET aliases = aliases`)는 남기지 않는다.
- 트리거 함수는 `SECURITY DEFINER`(주인 `career`)로 만들어, 팀원에게 기록 표 쓰기 권한이 없어도 기록되게 한다. 팀원은 기록 표를 **읽기만** 한다(지우거나 고칠 수 없게).
- 마이그레이션이 처음 채우는 61개 낱말 같은 것도 기록에 남아도 괜찮다.

**기술의 대표 능력 — `tech_capability`에 칸 하나 추가** *(내 판단)*
- 지금은 JSON에서 기술의 **첫 번째 능력**이 대표 능력이다. LLM이 `기타: RDS`처럼 적으면 그 기술의 대표 능력으로 이어서 `requirement.capability_id`에 저장한다(`extract_skills.other_capability()`). DB의 `tech_capability`는 (기술, 능력) 쌍뿐이라 "첫 번째"를 담을 곳이 없다. 능력이 2개 이상인 기술은 27개이고, 그중 23개는 능력ID 순으로 읽으면 대표가 바뀐다(예: RDS 클라우드 → 관계형 DB).
- → `tech_capability.is_primary`(대표 능력, boolean, NOT NULL, 기본값 false)를 더한다. 기술마다 대표는 최대 하나(부분 UNIQUE 색인). 시드는 지금 JSON의 첫 번째 능력을 대표로 넣어 **지금과 똑같이** 동작하게 한다.
- 팀원이 대표를 안 정했으면(그 기술에 `is_primary`가 하나도 없으면) 능력ID가 가장 작은 것을 대표로 쓴다. 팀원이 깜빡해도 추출은 돈다.
- 능력 목록 순서(LLM 지시문 줄 순서)와 능력별 예시 기술 순서는 ID 순으로 읽는다. 시드가 JSON 순서대로 넣으므로 지금과 같고, 새로 넣은 것은 뒤에 붙는다.

### 4-2. 사전 판(버전) *(내 판단)*
- 사람이 판 번호를 올리지 않는다. 추출을 시작할 때 **읽은 사전 내용으로 지문**(정렬한 JSON의 SHA-256 앞 12자리, `prompt_version`과 같은 방식)을 만들어 `extraction_run.dict_version`에 남긴다.
- `dictionary_version` 표는 뜻을 바꿔 **"추출에 쓰인 사전 판과 처음 쓴 시각"**을 남긴다(추출이 새 지문을 처음 쓸 때 한 줄). 칸 이름·설명(COMMENT)도 맞게 고친다. 변경 기록과 합치면 그 판이 어떤 사전이었는지 되짚을 수 있다.

### 4-3. 추출이 DB 사전을 읽기
- `CapDict`가 DB에서 사전을 만들 수 있게 한다. **사용 중(`is_active`)인 능력·기술만** 쓴다.
- `extract_skills.py`는 지금 import할 때 파일로 사전(`CD`)과 JSON 스키마(`enum`)를 만든다. → **추출을 시작할 때 DB에서 한 번 읽어** 만들게 바꾼다(한 번 실행 안에서는 같은 사전).
- Airflow 추출 태스크(`pipeline_tasks.step_extract` → `extract_skills.py` 하위 프로세스)는 이미 DB 주소를 받으므로 그대로 쓴다.

### 4-4. 빈 DB 채우기와 내려받기
- `db_load.py sync-dict`(파일 → DB)는 없앤다.
- **`db_load.py export-dict`**(새 명령): 지금 접속한 DB(aws 브랜치면 RDS)의 사전 4개 표(`capability`, `tech`, `tech_capability`, `exclude_word`)를 **`db/seed_dictionary.sql`**로 내려받는다. *(파일 이름은 내 판단)*
  - 이 SQL은 **사전이 비어 있을 때만** 채운다(이미 사전이 있는 DB에서는 아무것도 안 함 → 팀원이 지운 항목이 되살아나지 않음).
  - 같은 사전이면 같은 파일이 나오게(정렬) 해서, Git 차이로 무엇이 바뀌었는지 보이게 한다.
- `db_load.py init`은 `schema.sql` 뒤에 `seed_dictionary.sql`을 적용한다. 테스트 도구(`tests/conftest.py`)도 마이그레이션 뒤에 적용한다.
- 처음 `seed_dictionary.sql`은 지금 `capabilities.json` 내용으로 만든다(지금 RDS 사전과 같음).

### 4-5. 팀원이 사전을 잘못 고쳤을 때 *(내 판단)*
- DB 제약이 막는 것(없는 능력 가리키기, 추출 결과가 쓰는 능력 지우기 등)은 그대로 막힌다.
- **항목 몇 개가 어긋남**(예: 같은 별칭을 두 기술에 넣음, 상위 고리가 돌아 제자리로 옴): 추출이 사전을 읽을 때 찾아, **추출은 멈추지 않고** Slack(`#data-pipeline`)에 어긋난 항목을 알린다. 어긋난 항목을 어떻게 다룰지(예: 먼저 나온 것 쓰기)는 만드는 사람이 정한다.
- **사전이 통째로 망가짐**(사용 중인 능력이 0개, 또는 `기타` 능력이 없거나 꺼짐 — 예: WHERE 없이 `UPDATE capability SET is_active = false`): 그날 **추출을 멈추고** Slack에 알린다. 망가진 사전으로 뽑은 결과는 다시 맞추지 않으므로(결정 3) DB에 남으면 안 된다. 멈춰도 잃는 것은 없다 — 추출 결과가 없는 진행 공고는 '밀린 공고'라 사전을 고친 다음 날 다시 뽑힌다. 고칠 때는 변경 기록(`dictionary_change`)의 예전 값을 본다.
- "마지막 정상 사전으로 돌리기"는 하지 않는다(사전 판마다 내용 전체를 저장해야 해서 무거움).
- `TRUNCATE`는 줄마다 걸리는 트리거를 거치지 않는다. 팀원에게는 `TRUNCATE` 권한이 없지만, 기록이 빠지지 않게 사전 표에서 `TRUNCATE`를 막거나 기록하는 방법은 만드는 사람이 정한다.

### 4-6. RDS·로컬 DB 적용과 권한
- 마이그레이션 `004`를 RDS와 로컬 `career-db`에 적용한다(README의 "번호 순서대로 적용").
- RDS 팀원 권한: `exclude_word`는 읽기·쓰기(사전 표와 같음), `dictionary_change`는 읽기만.

### 4-7. 문서
- ERD 그림 2개(svg 고친 뒤 png는 Chrome headless 2배로 다시 만듦 — 지금까지 방식), `physical-design.md`(표 설명, 바꾼 날 기록), README(사전 고치는 법, `export-dict`, RDS 지우기 전 내려받기), `capabilities.json`을 가리키던 설명들(`capdict.py`, `extract_skills.py` 머리말 등).

## 5. 만드는 사람에게 맡기는 것
- `CapDict`를 DB에서 만드는 구체적인 방법(쿼리, 파일 경로 인자 정리)
- 테스트에서 사전을 어떻게 줄지(시드 SQL로 채운 임시 DB를 쓸지, 작은 가짜 사전을 쓸지)
- `seed_dictionary.sql`의 정확한 모양(INSERT 묶음, "비어 있을 때만" 확인 방법)
- 어긋난 사전 항목을 찾는 규칙의 세부와 Slack 문구
