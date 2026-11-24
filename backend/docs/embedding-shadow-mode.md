# 공고 유사도 Embeddings SHADOW_MODE 설계

상태: **설계 확인 후 SHADOW_MODE 구현·격리 검증 진행**. 실제 OpenAI 호출은 수행하지 않았다. 최종 확인 결과는 [검증 보고서](verification/embedding-shadow-verification.md)에 기록한다.

조사 기준: 2026-11-09 10:47 KST, `feature/BE`의 기존 키워드 정책 `keyword-mvp-2`, 직무 사전 `roles-mvp-2`. 아래 예비 집계는 최초 설계 시점의 기록이며 구현 후 dry-run 집계는 검증 보고서에 구분한다.

## 1. pgvector와 권한 확인

명시적인 READ ONLY / REPEATABLE READ 트랜잭션으로 기존 RDS를 조사했고 종료 전 read-only=on을 다시 확인했다. 조회 후 rollback했으며 DDL·데이터 변경·확장 설치는 실행하지 않았다.

| 확인 항목 | 결과 |
|---|---|
| `pg_available_extensions`의 vector | 0.8.1 설치 가능 목록에 존재 |
| `pg_extension`의 vector | 설치되지 않음 |
| vector 타입·cosine 함수 | 없음 |
| 사용 계정의 public CREATE | 가능 |
| requirement·recruit_unit 등 원본 테이블 SELECT/REFERENCES | 가능 |
| 기존 embedding/semantic 테이블 | 없음 |
| 복수 current extraction 공고 | 0개 |

현재 환경에서는 **`real[]` 저장 + 애플리케이션 cosine**을 사용한다. vector가 이미 설치돼 있고 타입 USAGE·필요 함수 EXECUTE가 확인된 다른 환경에서만 vector 경로를 선택한다. 설치 가능 목록에 있다는 이유로 CREATE EXTENSION을 실행하지 않는다. SHADOW 1차는 이미 선정된 후보만 비교하므로 ANN 인덱스가 필요하지 않다.

## 2. 대상 행과 API 입력 견적

| 구분 | 행/문장 수 |
|---|---:|
| 전체 이력 requirement | 41,508 |
| current extraction의 IT requirement | 40,233 |
| REQUIRED / 필수 | 10,946 |
| PREFERRED / 우대 | 10,405 |
| DUTIES / 업무 | 16,036 |
| 세 범주 원본 합계 | 37,387 |
| 예비 제외 후 requirement | 33,075 |
| 예비 제외 후 REQUIRED / PREFERRED / DUTIES | 9,802 / 9,075 / 14,198 |
| 예비 고유 입력 문장 | 28,354 |
| 문장 수 64개 기준 최소 HTTP 요청 수 | 444 |

전체 current IT 모집 단위는 2,496개이며, 세 범주와 예비 필터를 통과한 모집 단위는 2,407개다. 예비 제외 내역은 활성 기술 없는 미분류 요건 3,160행, 직무 모호 1,022행, 학력·태도 표현 88행, 회사명 포함 42행이다.

위 33,075행·28,354문장은 **설계용 예비 집계**다. 정식 전처리의 비식별 검사·Java 직무 매핑 동등성·토큰 한도 검증을 완료한 확정 호출량은 아니다. 현재 임베딩 캐시는 없어 최초 생성 시 예비 고유 입력 전체가 미생성 대상이다. 실제 요청 수는 토큰 패킹과 제외 결과에 따라 달라진다. 조사 중 OpenAI 호출은 0회다.

## 3. 입력·전처리 계약

전처리 버전은 `requirement-input-v1`, 비교 정책은 `semantic-shadow-v1`, 모델 설정 버전은 `embedding-config-v1`로 분리한다. 기본 모델은 `OPENAI_EMBEDDING_MODEL` 환경변수의 `text-embedding-3-small`, 기본 차원은 1,536이다. 모델 설정에는 차원·float 인코딩 등 실제 생성 인자를 포함해 설정 변경 시 캐시를 분리한다. 공급자 모델 alias를 불변 snapshot이라고 주장하지 않는다.

고정 입력 형식:

```text
[backend][REQUIRED] capability=백엔드 프레임워크; tech=Spring Boot; text=Spring Boot 기반 REST API 개발
```

입력 생성 순서:

1. current extraction, IT 모집 단위, 필수/우대/업무만 읽고 requirement ID별로 연결 tech를 집계한다. 같은 requirement가 여러 tech에 연결돼도 한 문장이다.
2. 직무는 기존 `posting-similarity.properties`를 원본으로 하고 모집 단위명 → 공고 직무 → 제목의 기존 순서와 모호성 차단을 유지한다. 이 metadata는 직무 코드 판별에만 사용하고 입력에는 직무 코드만 넣는다. Python·Java 교차 fixture로 결과 일치를 검증한다.
3. Unicode NFKC, 줄바꿈·공백·제어문자 처리, 구두점/구분자 escape 규칙을 고정한다. 기술명은 활성 표준 name만 사용하고 중복 제거 후 UTF-8 바이트 순으로 정렬한다. Java/JavaScript, C/C++, C# 같은 기술을 부분 일치로 합치지 않는다.
4. 회사명·학력·경력 연수·태도·개인정보·HTML을 입력에서 제외한다. 기술 역량이 없는 기타 요건과 판별 불명확한 직무는 제외한다. 혼합 문장·인명/회사/학교/연락처 위험을 안전하게 분리할 수 없으면 해당 요건을 제외하고 사유 코드만 집계한다. 원본 HTML·quote·프로필을 전송하지 않는다.
5. 계획·학습·부정과 실제 구현·운영을 구분하는 서술은 보존한다. 경력 연수 제거를 이유로 '학습 예정'을 '구현 경험'으로 바꾸지 않는다. 회사명 제거는 기술 이름의 임의 치환이나 유사어 확장이 아니다.
6. `input_hash = SHA-256(최종 입력의 UTF-8 바이트)`로 고정한다. requirement ID는 hash에 넣지 않아 동일 문장을 다른 요건에서도 재사용한다. 캐시 식별자에 모델·설정 버전·차원·전처리 버전을 함께 포함한다.

실제 API 키는 Python 실행 시 `OPENAI_API_KEY` 환경변수에서만 읽는다. .env 자동 탐색, 하드코딩, CLI 키 인자, Java로의 키 전달은 하지 않는다. 키가 없어도 dry-run과 기본 Mock 테스트는 실행 가능해야 한다.

## 4. 신규 소유 테이블

migration은 `db/migrations/09-requirement-embedding-shadow.sql` 템플릿과 Python 전용 실행기를 사용한다. 기존 public 테이블에 ALTER·UPDATE·DELETE를 실행하지 않는다. 신규 객체는 실행 계정이 소유하고 원본 ID는 REFERENCES 권한으로 연결한다.

| 객체 | 주요 필드·역할 |
|---|---|
| `public.be_embedding_cache` | 모델명·설정 버전·차원·전처리 버전·input_hash·embedding·상태·안전한 오류 코드·created_at·updated_at. 동일 문장의 벡터를 한 번만 보관 |
| `public.be_requirement_embedding` | requirement_id·recruit_unit_id·category·source_run_id·role_code·source_fingerprint·cache_id·created_at·updated_at. 원본 요건과 캐시 연결 |
| `public.be_embedding_request` | 배치 ID·input_hash 순서·상태·시도 수·안전한 오류 코드·토큰 사용량·가격 기준·추정 비용. API 전송과 결과 확정 기록 |
| `public.be_requirement_embedding_view` | 연결과 캐시를 조인해 요청한 필수 메타데이터 전체와 벡터 제공 |
| `public.be_embedding_source` | current IT 요건과 활성 tech를 읽는 공통 원본 뷰 |
| `public.be_embedding_schema_migration` | 설치 버전·SQL checksum·실제 저장 타입 기록 |

뷰에는 requirement_id, recruit_unit_id, category, model_name, model_revision(설정 버전), embedding_dimension, preprocessing_version, input_hash, embedding, created_at, updated_at이 모두 포함된다. 모델별 hash 유일성을 캐시에서 강제하면서 한 문장에 여러 requirement가 연결될 수 있도록 물리 테이블을 분리한다.

- 캐시 UNIQUE: `(model_name, model_revision, embedding_dimension, preprocessing_version, input_hash)`.
- 연결 UNIQUE: `(requirement_id, model_name/설정/전처리 구성)`에 해당하는 현재 연결. 벡터는 캐시 FK로 참조한다.
- category CHECK는 REQUIRED/PREFERRED/DUTIES. real[]는 단일 차원·원소 수·NULL 금지를 검사하고 Python/Java에서 유한값·정확한 차원·0이 아닌 norm을 검증한다.
- 과거 캐시와 성공 데이터는 실패 때문에 삭제하지 않는다. 원본 문장·사전·직무·추출 실행이 바뀌어 fingerprint가 달라진 연결은 조회에서 STALE로 제외한다. 기존 벡터를 새 문장의 벡터처럼 사용하지 않는다.

## 5. Python 생성 배치와 중복 방지

별도 `data-pipeline/requirement-embeddings/` 패키지를 둔다. 기존 공고 크롤러나 HTTP GET이 OpenAI를 호출하지 않는다.

```text
READ ONLY 원본 snapshot → 정규화·제외 → hash 중복 제거
→ 기존 READY 캐시 재사용 → 신규 hash 원자적 claim·전송 기록 commit
→ 문자열 배열로 Embeddings API 호출
→ 응답 index·모델·개수·차원·유한값 검증
→ 캐시 저장 commit → 아직 current인 requirement 연결
→ 안전한 집계 보고서
```

초기 요청 한도는 64문장, 요청 합계 8,192토큰, 문장당 2,048토큰, 동시 요청 1개를 제안한다. tokenizer로 세며 초과 입력을 조용히 자르지 않고 제외한다. 모델/API 자체의 상한보다 보수적인 작업 한도다.

요청 position → input_hash → requirement ID 목록을 기록한다. 응답 배열의 물리 순서를 믿지 않고 `data[].index`로 복원한다. index 중복·누락·범위 초과는 응답 매핑 오류로 처리한다. 모델·차원 오류나 실패가 있어도 이전 성공 배치와 기존 키워드 데이터는 유지한다. 같은 hash의 동시 claim은 DB 잠금·유일성 제약으로 막는다. READY 캐시는 재실행 시 API 호출 없이 사용한다.

**API 완료와 DB 저장 사이의 장애까지 포함한 무조건적인 exactly-once 호출은 보장할 수 없다.** Embeddings API의 idempotency 보장을 가정하지 않는다. SDK 자동 재시도는 끄고, 전송 후 timeout·프로세스 중단·저장 실패로 처리 여부가 불확실하면 `UNKNOWN/DELIVERY_UNCERTAIN`으로 남겨 자동 재전송하지 않는다. 확정 실패와 불확실 상태는 별도의 명시적 재시도/정리 절차로 구분한다. 이 방식으로 자동 재실행에 의한 중복 호출을 막되, 불확실 항목은 운영 확인이 필요함을 보고한다.

오류는 AUTH_FAILED, RATE_LIMITED, DELIVERY_UNCERTAIN, RESPONSE_MAPPING_INVALID, MODEL_MISMATCH, DIMENSION_MISMATCH, INVALID_VECTOR, DB_SAVE_FAILED 등 고정 코드만 기록한다. SDK 예외 원문·Authorization·입력 본문을 로그나 검증 보고서에 쓰지 않는다.

## 6. SHADOW_MODE 비교·응답

기존 `PostingCandidateSelectionService`가 후보·HIGH/LOW·순위를 확정한 다음 `ComparisonCandidatesQueryService`에서 별도 shadow service로 후보 최대 5개를 보강한다. `PostingSimilarityScorer` 구현체를 교체하거나 새 Bean으로 경쟁시키지 않는다. 기존 eligibility, comparator, 회사·공고 제한, tech ID·alias 정확 일치를 그대로 둔다.

범주 K마다 현재 문장·동일 모델/설정/전처리 버전의 유효 벡터만 사용한다.

```text
semantic_K(T,C) = mean over target requirements t of max over candidate requirements c cosine(t,c)
```

REQUIRED↔REQUIRED, PREFERRED↔PREFERRED, DUTIES↔DUTIES만 비교한다. 후보 문장의 중복 선택을 금지하는 일대일 매칭이 아니라, 대상 요건별 최고 후보 요건을 선택하는 방향성 비교다. cosine 원래 값(-1~1)을 보존하고 키워드 점수와 합산하지 않는다. 임계값·새 HIGH/LOW·semantic rank는 만들지 않는다.

벡터 쌍이 없으면 해당 범주는 null이다. 부분 생성이면 비교 가능한 쌍만 평균을 내되 상태를 PARTIAL로 표시한다. `semanticMatchedRequirementCount`는 세 범주에서 비교가 가능했던 대상 requirement 수이며 임계값을 통과한 의미 일치 개수라는 뜻이 아니다. 범주별 입력/생성/누락 개수는 검증 보고서에 별도로 기록한다.

각 candidate에 추가할 필드 예시(임베딩 미생성):

```json
{
  "embeddingStatus": "NOT_GENERATED",
  "embeddingModel": "text-embedding-3-small",
  "embeddingPolicyVersion": "semantic-shadow-v1",
  "requiredSemanticSimilarity": null,
  "preferredSemanticSimilarity": null,
  "dutiesSemanticSimilarity": null,
  "semanticMatchedRequirementCount": 0
}
```

상태는 OFF의 DISABLED, 미생성 NOT_GENERATED, 계산 READY, 부분 PARTIAL, 오래된 연결 STALE, 조회/생성 오류 UNAVAILABLE로 구분한다. SHADOW_MODE만 활성화할 수 있고 실제 순위 반영 모드는 이 버전에 제공하지 않는다. 새로운 필드의 null을 0으로 바꾸지 않는다.

임베딩 조회는 원본 선정 snapshot의 run ID를 전달받아 별도의 짧은 READ ONLY 트랜잭션에서 확인한다. DB 오류를 기존 트랜잭션 안에서 단순 catch하면 PostgreSQL transaction-aborted 상태가 남을 수 있으므로, 독립 트랜잭션 경계 밖에서 실패를 흡수한다. 조회 timeout은 UNAVAILABLE/null, 저장소 미설치·해당 모델/차원 미생성은 NOT_GENERATED/null이며 기존 응답과 순위를 유지한다. HTTP GET에서 OpenAI 키나 외부 API는 사용하지 않는다.

## 7. 변경 파일

| 범위 | 예정 파일 |
|---|---|
| 설계·검증 | 이 문서, `backend/docs/verification/embedding-shadow-verification.md` |
| Python 독립 배치 | `data-pipeline/requirement-embeddings/`의 config, source, preprocessing, client, repository, batch, migrate, benchmark 및 실행 README |
| 벤치마크 | 동일 패키지의 합성·비식별 문장 쌍 fixture와 Mock/선택 smoke 테스트 |
| DB | `db/migrations/09-requirement-embedding-shadow.sql` |
| Java 읽기·계산 | `domain/posting/embedding/`의 ShadowEmbeddingRepository, ShadowEmbeddingService, CosineSimilarity, 설정 클래스 |
| 응답 보강 | `ComparisonCandidatesQueryService.java`, `ComparisonCandidatesResponse.java`, OpenAPI 예시 |
| 설정 | embedding 전용 properties, `OPENAI_EMBEDDING_MODEL` 기본값 연결. 실제 키 설정 파일 없음 |
| 회귀 | 기존 후보 API 회귀와 임베딩 전용 PostgreSQL/Mock 테스트, 검증 실행기·CI의 새 테스트 연결 |

조사 스크립트와 집계 JSON은 커밋하지 않는 work/에 둔다. 원본 pipeline, 기존 keyword scorer·eligibility·순위 설정은 변경 대상이 아니다. Python 실행 방법은 [배치 README](../../data-pipeline/requirement-embeddings/README.md)를 따른다.

## 8. 테스트·영향 없음의 근거

기본 테스트는 실제 API를 호출하지 않는다. 실제 키 대신 비밀이 아닌 테스트용 sentinel과 Mock을 사용한다.

- 동일 입력·동일 구성 재사용, 변경된 문장만 새 요청, 다른 requirement의 동일 hash 공유.
- 응답 순서 뒤집힘, index 누락/중복/초과, 모델/차원 오류, 0·NaN·Infinity 벡터 차단.
- REQUIRED/PREFERRED/DUTIES 분리, 비교 문장 없음의 null, 부분 생성 상태와 비교 개수.
- Java와 JavaScript를 별도 tech로 유지. 임베딩이 높은 유사도를 반환해도 ID 교집합을 만들지 않음.
- API 실패·키 없음·임베딩 테이블 없음·DB 조회 실패에도 기존 키워드 응답이 정상.
- OFF와 SHADOW 응답에서 추가 7개 필드를 제거한 JSON을 비교해 후보 ID·순서·rank·HIGH/LOW·기존 점수·사유가 동일함을 검증.
- GET 전후 원본 public 테이블 전체 행 수·해시·시퀀스 불변. 배치/migration도 신규 소유 테이블만 변경함을 격리 DB에서 검증.
- 예외에 테스트 sentinel이 포함돼도 로그·오류·보고서에 남지 않음. 기본 테스트와 CI는 실제 OpenAI 키를 읽거나 요구하지 않음.
- 정상 재실행 중복 호출 없음, 동시 실행 claim 충돌, 전송 결과 불확실 상태의 자동 재호출 금지.

합성 benchmark는 같은 의미/다른 표현, 관련 있으나 수준 차이, 무관 역량, Java/JavaScript, Docker 사용/운영, 학습 예정/실제 구현 경험의 6유형을 포함한다. 아직 임계값이나 의미 정확도 합격선을 설정하지 않는다.

실제 smoke는 `RUN_OPENAI_EMBEDDING_SMOKE=1`일 때만 합성 문장 최대 10개를 보낸다. request 수, API usage 토큰, 가격 기준·시각, 추정 USD를 기록한다. 추정 비용을 실제 청구 금액이라고 표시하지 않는다. 기본 실행에서는 skip 가능하며 실제 키 값은 요청·출력하지 않는다.

기존 후보 선정이 끝난 이후의 독립 보강이므로 임베딩 값·준비 상태·실패는 후보 선별·HIGH/LOW·순위에 입력되지 않는다. 이 구조와 전체 응답 동등성 테스트를 영향 없음의 근거로 삼는다.

## 조사 근거와 공식 문서

- 로컬 집계: `work/embedding-shadow-design-audit.json`, `work/embedding-shadow-input-estimate.json`. 원문·키는 보고서에 포함하지 않는다.
- [OpenAI Embeddings 생성 API](https://developers.openai.com/api/reference/python/resources/embeddings/methods/create): 배열 입력, 응답 index, 요청 토큰 제한.
- [OpenAI Embeddings 가이드](https://developers.openai.com/api/docs/guides/embeddings): text-embedding-3-small 기본 차원 1,536.
- [text-embedding-3-small 모델](https://developers.openai.com/api/docs/models/text-embedding-3-small): 모델·가격 정보. 실제 smoke 시점의 공식 가격을 확인해 사용량 기반 추정치를 기록한다.
