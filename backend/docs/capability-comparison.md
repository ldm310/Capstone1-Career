# 채용공고 역량 비교 API

기존 추출 코드, positions/required/preferred/duties/other/skipped JSON 계약과 기존 상세·fit API는 변경하지 않는다. 원본 추출 테이블에는 쓰지 않는다.

## 파일과 역할

| 파일 (backend/src 기준) | 역할 |
| --- | --- |
| main/java/com/career/backend/domain/posting/PostingResultAdapter.java | 원본 계약용 입력 record와 정규화된 상세 DTO를 서비스 DTO로 변환 |
| main/java/com/career/backend/domain/posting/RequiredConditionRules.java | 조건 enum과 모든 조건 판별 패턴 |
| main/java/com/career/backend/domain/posting/ComparisonTarget.java | 모집 단위별 표준 직무군·경력 구간 |
| main/java/com/career/backend/domain/posting/SuccessfulApplication.java | 인증된 합격 이력 모델 |
| main/java/com/career/backend/domain/posting/ComparisonTargetRepository.java | 비교 기준 조회 |
| main/java/com/career/backend/domain/posting/SuccessfulApplicationRepository.java | 인증·단계·날짜·직무·경력 필터 조회 |
| main/java/com/career/backend/domain/posting/ApplicantReferenceService.java | 비교군 선택·사용자 중복 제거·역량 집계 |
| main/java/com/career/backend/domain/posting/CapabilityComparisonService.java | 공고·Adapter·사용자 Evidence·비교군 조합 |
| main/java/com/career/backend/api/posting/CapabilityComparisonController.java | 신규 GET 엔드포인트 |
| main/java/com/career/backend/domain/job/ExtractionRun.java (수정) | 기존 llm_output_raw JSON 읽기 전용 매핑과 skipped 조회 |
| main/java/com/career/backend/domain/profile/UserSkillEvaluationRepository.java (수정) | 선택된 사용자들의 평가를 일괄 조회 |
| test/java/com/career/backend/domain/posting/PostingResultAdapterTest.java | 조건/혼합 문장/카테고리/빈 배열/중복/원본 보존 |
| test/java/com/career/backend/domain/posting/CapabilityComparisonTest.java | 실제 H2 DB 조회·선택·필터·집계·API·원본 JSON 보존 |
| ../../db/init/03-capability-comparison.sql | 신규 테이블과 조회 색인; 기존 DB에 별도 적용 필요 |

## 데이터 흐름

추출 JSON → 기존 파이프라인 저장 → job.extraction_run/recruit_unit/unit_item/requirement/requirement_tech → 기존 ExtractionTreeLoader → 새 PostingResultAdapter → 새 비교 API.

profile.comparison_target → 인증 합격 이력 필터 → 동일 회사 후보 → 부족하면 전체 시장 후보 → 표준 capability ID별 저장된 프로젝트 평가 집계.

사용자 평가 → 기존 UserCapabilityService → 최고 점수·LV·프로젝트별 Evidence를 userCapabilities로 반환.

requiredSkills와 preferredSkills만 각각 필수/우대 비교 기준이다. dutySkills와 environmentSkills는 참고 정보다. requiredConditions는 표시용이며 LV를 계산하거나 변경하지 않는다. 합격 확률은 계산하지 않는다.

원본 JSON을 직접 변환하는 경우 `PostingResultAdapter.adapt(Extraction, Map<String, Long>)`를 사용한다. Map은 표준 capability 사전의 이름→ID이며, ID를 모르면 null을 유지한다. API는 DB에 저장된 표준 ID를 사용한다.

## 실행

Java 21이 필요하다. 신규 DB는 compose의 init 마운트가 SQL을 자동 적용한다. **이미 존재하는 DB 볼륨에는 init SQL이 다시 실행되지 않는다.** 기존 DB에는 운영 절차에 따라 `db/init/03-capability-comparison.sql`을 적용한다. 기존 job 스키마의 llm_output_raw 컬럼은 01 SQL에 이미 있다.

```powershell
Get-Content -Raw -Encoding utf8 db/init/03-capability-comparison.sql | docker compose exec -T db psql -U postgres -d career -v ON_ERROR_STOP=1
docker compose up -d --build backend
```

POSTGRES_USER를 변경했다면 psql 사용자도 맞춘다. 실제 DB 마이그레이션과 배포는 이번 작업에서 실행하지 않았다.

비교 기준은 모집 단위 ID에 대해 role_group(예: BACKEND), career_band(예: JUNIOR)를 등록한다. 합격 이력도 동일한 표준값을 사용한다. 이는 공고 제목에서 임의 추론하지 않는다. 새로운 추출 실행으로 unit ID가 바뀌면 새 기준을 등록해야 한다.

합격 이력은 verified=true, stage가 DOCUMENT_PASSED/INTERVIEW_PASSED/FINAL_PASSED인 것만 조회한다. accepted_at은 서울 기준 오늘부터 역산 3년 이내(양끝 포함)이며 미래 날짜는 제외한다. 현재 공고 합격 이력과 조회 사용자 자신도 제외한다.

최소 표본은 기본 5명이고 Spring 설정 `app.comparison.minimum-sample-size` 또는 환경 변수 `APP_COMPARISON_MINIMUMSAMPLESIZE`로 변경한다.

## API 및 프론트 예시

`GET /api/postings/1/capability-comparison?userId=100`

응답 형태 예시(데이터는 예시):

```json
{
  "postingId": 1,
  "userId": 100,
  "analyzed": true,
  "skippedAvailable": true,
  "userCapabilities": [{
    "capabilityId": 1, "capabilityName": "관계형 DB", "groupName": "데이터",
    "bestScore": 70, "level": "LV2",
    "projects": [{"projectId": 10, "projectName": "주문 API", "score": 70,
                  "level": "LV2", "evaluatedAt": "2026-11-04T09:00:00+09:00"}]
  }],
  "positions": [{
    "posting": {
      "unitId": 1, "positionName": "서버 개발자 (경력)", "career": "경력", "years": "3년 이상",
      "requiredSkills": [{"capabilityId": 1, "capability": "관계형 DB", "otherName": "",
                          "techs": ["MySQL"], "relation": "예시", "quote": "MySQL 등 관계형 DB 경험"}],
      "requiredConditions": [{"type": "CAREER_YEARS", "text": "개발 경력 3년 이상", "quote": "개발 경력 3년 이상"}],
      "preferredSkills": [], "dutySkills": [], "environmentSkills": [], "skipped": []
    },
    "reference": {
      "referenceType": "MARKET_SAME_ROLE", "referenceLabel": "BACKEND JUNIOR 합격자",
      "sampleSize": 6, "insufficientData": false, "reason": null,
      "attempts": [{"referenceType": "SAME_COMPANY_SIMILAR_ROLE", "sampleSize": 2, "insufficientData": true},
                   {"referenceType": "MARKET_SAME_ROLE", "sampleSize": 6, "insufficientData": false}],
      "capabilities": [{"capabilityId": 1, "capabilityName": "관계형 DB", "holderCount": 4,
                        "holderRate": 0.6666666666666666, "medianLevel": 2.5, "sampleSize": 6}]
    }
  }]
}
```

프론트는 capabilityId로 사용자 평가와 연결한다. requiredConditions는 기술 LV에서 제외한다. 비교군은 각 모집 단위별 참고 영역에 표시한다. NONE일 때 referenceLabel은 `비교 가능한 합격자 데이터 없음`, sampleSize=0, capabilities=[], insufficientData=true이며, attempts에는 실제로 조회된 부족 표본 수가 남는다. reason은 INSUFFICIENT_SAMPLE 또는 COMPARISON_TARGET_MISSING이다.

holderRate는 0~1 비율이고 분모는 평가가 없는 합격자도 포함한 고유 사용자 수다. 한 사용자의 여러 프로젝트는 최고 LV 하나로 합친다. LV0는 근거 부족이므로 보유자로 세지 않으며, medianLevel은 LV1 이상 보유자의 숫자 LV 중앙값이다(짝수 표본은 평균). 평가가 없는 역량을 임의로 LV0로 채우지 않는다. 평가된 보유자가 없는 역량은 집계 배열에서 제외한다.

중복은 필드별로 capability ID·이름·기타 이름·정렬된 기술 집합·관계·quote가 같은 항목을 제거한다. 같은 capability라도 다른 quote나 택1/모두 관계는 보존한다. 프론트는 이를 별도 사람이나 별도 능력으로 세지 말고 capabilityId로 묶어 표시한다.

## 테스트

```powershell
cd backend
.\gradlew.bat test
```

보고서: `backend/build/reports/tests/test/index.html`. 테스트는 H2 PostgreSQL 모드이며 실제 운영 PostgreSQL에서 마이그레이션 검증은 별도로 필요하다.

## 현재 한계

- 인증을 수행하거나 합격 이력을 수집·등록하는 API는 기존에 없으며 이번 범위에는 포함하지 않았다. 새로운 테이블에 검증된 이력과 비교 기준을 공급해야 한다. 자동 직무 표준화도 추가하지 않았다.
- 원본 JSON이 없는 과거 추출의 skipped는 복구할 수 없다. skipped=[]와 skippedAvailable=false로 구분한다. skipped는 원본 계약에서 공고 전체 항목이므로 각 position에 동일하게 전달한다.
- Evidence는 현재 저장된 프로젝트 ID/이름/점수/평가 시각까지 제공한다. PDF 원문 인용이나 기술별 상세 근거는 기존 평가 DB에 없어 생성하지 않는다.
- 조건 분리는 규칙 기반이며 text와 quote를 검사한다. 혼합 문장에서는 원문 전체를 조건 근거로 보존하면서 실제 capability/tech는 유지한다. 새 표현은 RequiredConditionRules에 추가한다.
- 기존 추출 파이프라인 최신 브랜치는 public 스키마를 쓰지만 현재 BE는 job 스키마를 사용한다. 이번 구현은 현재 BE 기준을 따르며 스키마 통합이나 추출 코드 변경을 수행하지 않는다.
- 비교 서비스는 기존 userId 조회 방식을 따른다. 인증/소유자 접근 제어 체계는 별도 도입이 필요하다.
