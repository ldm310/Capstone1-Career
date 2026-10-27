# 물리 설계 (PostgreSQL 17)

논리 설계([ERD](erd.png))를 실제 DB에 만들 수 있게 옮겼다.
- DDL: [`db/schema.sql`](../db/schema.sql)
- 시험: 2026-10-27, 시험용 PostgreSQL 17에서 표 12개가 오류 없이 만들어지고 제약이 동작하는 것을 확인했다.

표와 칸의 한글 이름은 DDL의 `COMMENT`로 DB 안에도 남겨 두었다.

## 정한 규칙

| 항목 | 규칙 | 예 |
|---|---|---|
| 이름 | 영어 소문자 + 밑줄(snake_case), 표 이름은 단수 | `posting`, `site_posting_no` |
| 기본 키 | 표마다 `id` (`bigint`, 자동 증가) | `posting.id` |
| 외래 키 | `<가리키는 표>_id` | `posting.company_id` |
| 정해진 값 | 한글 값 그대로 + `CHECK` (LLM 답과 같은 글자라 바꿀 필요 없음) | `career IN ('신입','경력','신입·경력','언급없음')` |
| 시각 | `timestamptz` (시간대 포함) | `collected_at` |
| 해시 | `char(64)` (SHA-256 16진수) | `raw_hash` |
| 비용 | `numeric(10,6)` (달러, 소수 6자리) | `0.003540` |
| JSON | `jsonb` (안쪽 검색 가능) | `llm_output_raw` |
| 별칭 | `text[]` (글자 목록) + GIN 색인 | `{RDBMS,RDB}` |

정해진 값을 영어 코드(`new`, `experienced`)로 바꾸려면 BE 팀과 맞춘 뒤 `CHECK`만 고치면 된다.

## 표와 칸

### ① 수집

**회사 `company`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 회사ID | `id` | bigint | PK |
| 회사 이름 | `name` | text | NOT NULL, UNIQUE |

**공고 `posting`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 공고ID | `id` | bigint | PK |
| 회사ID | `company_id` | bigint | NOT NULL, FK → company |
| 사이트 | `site` | text | NOT NULL, 기본값 '사람인' |
| 사이트 공고번호 | `site_posting_no` | text | NOT NULL, **UNIQUE(site, site_posting_no)** |
| 제목 | `title` | text | NOT NULL |
| 사람인 직무 분류 | `site_job_category` | text | |
| 경력 조건 | `career_condition` | text | |
| 최소 요구 연수 | `min_years` | smallint | 0~50 |
| 고용 형태 | `employment_type` | text | |
| 공고 형태 | `kind` | text | NOT NULL, 글/이미지/섞임 |
| 상태 | `status` | text | NOT NULL, 진행/마감, 기본값 '진행' |
| 마감일 | `deadline` | date | 상시채용이면 비움 |
| 원본 위치 | `raw_path` | text | NOT NULL |
| 원본 해시 | `raw_hash` | char(64) | NOT NULL |
| 수집 시각 | `collected_at` | timestamptz | NOT NULL, 기본값 지금 |
| 마지막 확인 시각 | `last_checked_at` | timestamptz | NOT NULL, 기본값 지금 |

**공고 이미지 `posting_image`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 이미지ID | `id` | bigint | PK |
| 공고ID | `posting_id` | bigint | NOT NULL, FK → posting |
| 순서 | `seq` | smallint | NOT NULL, 1 이상, UNIQUE(posting_id, seq) |
| 이미지 주소 | `url` | text | NOT NULL |
| 파일 위치 | `file_path` | text | NOT NULL |
| 남김 여부 | `kept` | boolean | 판정 전이면 비움 |
| OCR 결과 위치 | `ocr_path` | text | |

### ② 추출 결과

**추출 실행 `extraction_run`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 실행ID | `id` | bigint | PK |
| 공고ID | `posting_id` | bigint | NOT NULL, FK → posting |
| 모델 | `model` | text | NOT NULL |
| 프롬프트 버전 | `prompt_version` | text | NOT NULL |
| 사전 버전 | `dict_version` | text | NOT NULL |
| 입력 해시 | `input_hash` | char(64) | NOT NULL |
| 입력 토큰 | `input_tokens` | integer | NOT NULL, 0 이상 |
| 출력 토큰 | `output_tokens` | integer | NOT NULL, 0 이상 |
| 비용 | `cost_usd` | numeric(10,6) | NOT NULL, 0 이상 |
| 다시 부름 | `retried` | boolean | NOT NULL, 기본값 false |
| 확인 필요 사유 | `review_reasons` | jsonb | NOT NULL, 기본값 `[]`, 목록이어야 함 |
| 확인 결과 | `review_result` | text | 문제없음/고침 |
| 확인 시각 | `reviewed_at` | timestamptz | 확인 결과와 함께 채움(둘 다 있거나 둘 다 비거나) |
| 표준화 전 답 | `llm_output_raw` | jsonb | 2026-10-27 이전 결과는 비어 있음(그 뒤로는 항상 채움) |
| 현재 사용 | `is_current` | boolean | NOT NULL, 기본값 false, **공고마다 최대 하나** |
| 실행 시각 | `run_at` | timestamptz | NOT NULL, 기본값 지금 |

확인 필요 사유는 `[{"검사": 1, "내용": "경력 조건 '신입 · 경력' / 만든 자리: 신입만"}]` 모양으로 넣는다. 검사 번호는 1(신입·경력), 2(모집 직무), 3(빈 내용)이다.

**모집 단위 `recruit_unit`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 단위ID | `id` | bigint | PK |
| 실행ID | `run_id` | bigint | NOT NULL, FK → extraction_run |
| 순서 | `seq` | smallint | NOT NULL, UNIQUE(run_id, seq) |
| 이름 | `name` | text | NOT NULL |
| IT 직무 | `is_it` | boolean | NOT NULL |
| 경력 구분 | `career` | text | NOT NULL, 신입/경력/신입·경력/언급없음 |
| 연수 | `years_text` | text | NOT NULL, 기본값 '' |
| 최소 연수 | `min_years` | smallint | 0~50 |
| 최대 연수 | `max_years` | smallint | 0~50, 최소 연수 이상 |

**항목 `unit_item`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 항목ID | `id` | bigint | PK |
| 단위ID | `unit_id` | bigint | NOT NULL, FK → recruit_unit |
| 칸 | `category` | text | NOT NULL, 필수/우대/업무/기타 |
| 순서 | `seq` | smallint | NOT NULL, UNIQUE(unit_id, category, seq) |
| 개조식 한 줄 | `text` | text | NOT NULL |
| 근거 | `quote` | text | NOT NULL |

**요건 `requirement`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 요건ID | `id` | bigint | PK |
| 항목ID | `item_id` | bigint | NOT NULL, FK → unit_item |
| 능력ID | `capability_id` | bigint | NOT NULL, FK → capability |
| 기타 이름 | `other_name` | text | NOT NULL, 기본값 '' |
| 관계 | `relation` | text | NOT NULL, 예시/택1/모두/능력만 |

**요건 기술 `requirement_tech`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 요건기술ID | `id` | bigint | PK |
| 요건ID | `requirement_id` | bigint | NOT NULL, FK → requirement |
| 기술ID | `tech_id` | bigint | FK → tech, 사전에 없으면 비움 |
| 적힌 이름 | `written_name` | text | NOT NULL |

### ③ 표준화 사전

**능력 `capability`** · **기술 `tech`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 능력ID / 기술ID | `id` | bigint | PK |
| 이름 | `name` | text | NOT NULL, UNIQUE |
| 묶음 (능력만) | `group_name` | text | (`group`은 SQL 예약어라 피함) |
| 상위 능력ID / 상위 기술ID | `parent_id` | bigint | FK → 같은 표, 자기 자신은 안 됨 |
| 별칭 목록 | `aliases` | text[] | NOT NULL, 기본값 빈 목록 |
| 사용 여부 | `is_active` | boolean | NOT NULL, 기본값 true |

**기술-능력 `tech_capability`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 기술ID | `tech_id` | bigint | PK, FK → tech |
| 능력ID | `capability_id` | bigint | PK, FK → capability |

**사전 버전 `dictionary_version`**
| 한글 | 영어 | 자료형 | 제약 |
|---|---|---|---|
| 사전 버전 | `version` | text | PK |
| 동기화 시각 | `synced_at` | timestamptz | NOT NULL, 기본값 지금 |

## 업무규칙을 어디서 지키나

| 업무규칙 | 지키는 곳 |
|---|---|
| 같은 공고는 한 번만 | DB: `UNIQUE(site, site_posting_no)` |
| 공고마다 현재 사용 실행은 최대 하나 | DB: 부분 UNIQUE 색인 `extraction_run_one_current` |
| 경력 구분·칸·관계·상태 같은 정해진 값 | DB: `CHECK` |
| 결과가 가리키는 능력·기술은 지우지 않음 | DB: FK `ON DELETE RESTRICT` (+ 사전 동기화 코드는 `is_active=false`로 표시) |
| 확인 결과와 확인 시각은 함께 | DB: `CHECK` |
| 0~3년 공고만 수집, 교육생 제외 | 수집 코드 (`sample_random.py`의 `min_years`) |
| 원본 해시가 바뀌면 다시 추출 | 수정 확인 코드 (아직 없음) |
| IT 아닌 자리는 항목 없음 | 저장 코드 (`it_job=false`면 빈 목록) |
| "능력만"이면 요건 기술 없음 | 저장 코드 |
| 기타 이름은 능력이 '기타'일 때만 | 저장 코드 |

표 하나만 보고 판단할 수 없는 규칙은 저장 코드에서 지킨다. 다른 표를 함께 봐야 해서 `CHECK`로는 막을 수 없다.

## 지울 때

| 지우는 것 | 결과 |
|---|---|
| 추출 실행 | 그 아래 모집 단위 → 항목 → 요건 → 요건 기술이 **함께 지워짐** (CASCADE) |
| 공고 | 공고 이미지와 추출 실행(과 그 아래)이 함께 지워짐 |
| 회사 | 공고가 있으면 **막힘** (RESTRICT) |
| 능력·기술 | 결과가 가리키고 있으면 **막힘**. 대신 사용 여부를 false로 |

## 색인

PostgreSQL은 FK 칸에 색인을 자동으로 만들지 않는다. 그래서 자주 잇는 칸에 색인을 만들었다.

| 색인 | 쓰임 |
|---|---|
| FK 칸 전부 (`company_id`, `posting_id`, `run_id`, …) | 표 잇기(JOIN) |
| `posting (status, last_checked_at)` | 3일마다 수정 확인할 공고 고르기 |
| `requirement (capability_id)`, `requirement_tech (tech_id)` | 능력별·기술별 통계와 매칭 |
| `extraction_run_review_queue` (부분 색인) | 사람이 확인할 목록 (확인 필요 사유가 있고 아직 확인 안 함) |
| `capability/tech (aliases)` GIN | 별칭으로 찾기 ("스프링 부트" → Spring Boot) |

## 시험 결과 (2026-10-27)

| 시험 | 결과 |
|---|---|
| `schema.sql` 실행 | 오류 없음, 표 12개 |
| 지어낸 공고 1건 넣기 (공고 → 실행 → 자리 → 한 줄 → 요건 → 요건 기술) | 정상 |
| 사전에 없는 기술(기술ID 비움) 넣기 | 허용 |
| 같은 공고 두 번 넣기 | 막힘 |
| 현재 사용 실행을 공고에 둘 | 막힘 |
| 정해진 값이 아닌 경력 구분('주니어') | 막힘 |
| 결과가 가리키는 능력 지우기 | 막힘 |
| 확인 결과만 있고 확인 시각 없음 | 막힘 |
| 최소 연수 > 최대 연수 | 막힘 |
| 현재 사용이 아닌 실행 여러 개 (재추출 기록) | 허용 |
| 추출 실행 지우기 | 아래 데이터 함께 지워짐, 능력은 그대로 |

## 넣는 코드

[`db_load.py`](../db_load.py)가 이 표들을 채운다(사용법은 [README](../README.md#실행)).
- 시험(2026-10-27, 시험용 PostgreSQL 17, sample3):
  - 공고 20 · 이미지 21 · 추출 실행 19 · 자리 39 · 한 줄 307 · 요건 305 · 요건 기술 170. JSON에서 센 값과 같다.
  - 같은 것을 다시 넣으면 새로 들어가는 것이 0건이다.
  - 사전에서 기술을 빼고 동기화하면 그 기술은 지워지지 않고 사용 여부만 false가 된다.

## 통계

**공고 기준**으로 센다(2026-10-27 결정). 공고 하나에 자리가 여러 개여도 1로 친다. 예: "필수에 '관계형 DB'가 나온 공고 수".

```sql
SELECT c.name, count(DISTINCT e.posting_id) AS 공고수
FROM extraction_run e
JOIN recruit_unit u ON u.run_id = e.id AND u.is_it
JOIN unit_item i    ON i.unit_id = u.id AND i.category = '필수'
JOIN requirement r  ON r.item_id = i.id
JOIN capability c   ON c.id = r.capability_id
WHERE e.is_current AND c.name <> '기타'
GROUP BY c.name ORDER BY 공고수 DESC;
```

## 남은 일

- **영어 이름:** BE 팀과 이름 규칙을 맞춘다.
- **3일마다 수정 확인:** Airflow DAG를 짤 때 만든다. 공고를 다시 받아 `content_hash`로 비교하고, 바뀐 공고만 다시 추출한다.
- **통계용 조회(view):** 통계 화면을 만들 때 위 SQL을 바탕으로 만든다.
