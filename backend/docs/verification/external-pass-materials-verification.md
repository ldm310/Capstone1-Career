# 외부 합격자료 크롤러·API 통합 검증

검증일: 2026-11-05. 문서 통합일: 2026-11-08 (KST). 외부자료 PR 초안과 최종 JSON 증거를 통합했다. 문서 정리 과정에서 수집·DB 변경·테스트를 다시 실행하지 않았다.

공식 계약은 [외부 합격자료](../external-pass-materials.md), [기술 키워드 교집합](../external-pass-keywords.md), [크롤러 README](../../../data-pipeline/external-pass-crawler/README.md)를 참고한다.

## 검증 기준과 환경

| 항목 | 기록 |
|---|---|
| 크롤러 통합 커밋 | `a15437f00d2222d43aee6087c8dc38bb283545c6` |
| 기술별 수행 신호 커밋 | `d2fe04927290f5f178b9764545cefcf548ca4f63` |
| 키워드 API·최종 이미지 기준 | `e76c45295f16e3c225adf053f8c54661190c8f85` |
| Backend 테스트 | 51건 통과, 실패·오류·skip 0건 |
| 크롤러 테스트 | 41건 통과, 실패·오류·skip 0건 |
| 수집 테스트 | 로컬 PostgreSQL의 합성 회사·공고 fixture, 공개 자료 5건 |

이 기록은 당시 `job` 공고 스키마를 사용한 로컬 통합 검증이다. 현재 구현은 `public` 스키마를 사용하며 전환 계약은 [public 통합 문서](../public-schema-integration.md)에 있다. 이 과거 실험을 현재 public 환경에서 다시 실행한 결과로 해석하지 않는다. 현재 API의 동일 회사·명시적 연결·IT_SW·EXCLUDED 제외 조건은 문서 정리 시 코드와 대조했다.

## 수집과 중복 실행

| 테이블 | 실행 전 | 1차 수집 후 | 재실행 후 |
|---|---|---|---|
| external_data.company_collection | 0 | 1 | 1 |
| external_data.pass_material | 0 | 5 | 5 |
| external_data.posting_pass_material | 0 | 5 | 5 |

회사 상태는 READY, minimumSampleSize=5, attemptCount=1이었다. 재실행은 READY 자료를 재사용했고 회사 재수집이나 중복 자료·중복 연결은 발생하지 않았다. 재연결 upsert로 연결 시각과 시퀀스 할당은 달라질 수 있으므로 크롤러 재실행 전체를 내용 불변으로 주장하지 않는다.

content는 허용된 기술명과 수행 코드만 포함하는 JSON 문자열이었다. 원문·개인정보를 저장하지 않는 검증을 통과했다. 기술 언급과 수행 코드는 검증된 기술 보유나 합격 원인이 아니다.

## 조회 API와 배포 산출물

| 요청 | HTTP | 확인 내용 |
|---|---|---|
| GET /api/postings/1/external-pass-materials | 200 | READY, 자료 5건, 페이지 정보 정상 |
| GET /api/postings/1/external-pass-keywords | 200 | 자료별 고유 기술 ID 언급 수와 독립 집계 일치 |
| Health | 200 | UP |
| Swagger UI | 200 | UI 제공 |
| /v3/api-docs | 200 | API 문서 제공 |

필수 교집합의 자료 수는 tech ID 1에서 3건, ID 2에서 2건이며 우대 ID 3은 1건이었다. externalOnly는 빈 배열이었다. 테스트 기술 사전이 제한적이어서 나머지는 unmappedKeywords에 남았다. 실제 수집 배열에는 같은 키워드의 중복이 없어, 중복 입력 처리는 Backend 자료별 HashSet 코드와 독립 DISTINCT 집계로 확인했다. 실수집 내용에 중복을 삽입해 시험하지 않았다.

초기 실행 중이던 구형 Backend에는 API 클래스가 없어 404가 났다. 현재 소스로 이미지를 빌드한 뒤 두 API·Health·Swagger가 모두 200이 됐으며 임시 Backend와 기존 서비스 경로의 키워드 결과도 일치했다. 이는 당시 이미지 문제 해결 기록이며 현재 코드의 미해결 404가 아니다.

API 조회 전후 당시 `job`·`external_data` 테이블의 행 수와 내용 해시는 동일했다. 크롤러의 의도된 저장과 GET 조회의 불변 검증을 구분한다. 임시 Backend 종료 후 별도 승인된 후속 정리에서 로컬 합성 fixture를 제거했고, 정리 결과는 아래 증거에 보존돼 있다. 이번 문서 정리에서는 DB를 변경하지 않았다.

## 근거와 한계

- 수집·중복 실행 결과 (`work/external-pass-integration-1990060f-52e9-4506-9e8e-9b4f22778649/integration-result.json`; 로컬 검증 산출물, 커밋 제외)
- 독립 집계·GET 불변 검증 (`work/external-pass-integration-1990060f-52e9-4506-9e8e-9b4f22778649/api-validation.json`; 로컬 검증 산출물, 커밋 제외)
- 최종 Backend 이미지·API 검증 (`work/backend-8080-verification-2a300902-6545-40ba-9c6f-9a48107436c5/verification.json`; 로컬 검증 산출물, 커밋 제외)
- 테스트 집계·로컬 fixture 정리 결과 (`work/cleanup-pr-verification-d4dd972d-bb29-4253-ba99-a0db9457dc15/final-result.json`; 로컬 검증 산출물, 커밋 제외)

로컬 검증은 통과했다. 전체 기술 사전과 실제 운영 환경의 접근·수집 정책 검증은 별도다. 현재 타사 comparison-candidates 결과를 기존 동일 회사 외부자료 연결에 자동 저장하는 기능은 포함하지 않는다. LV·합격 확률은 계산하지 않는다.
