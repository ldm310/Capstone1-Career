# 백엔드 API 목록 (2026-11-19)

Spring의 등록 작업 20개. Swagger `/swagger-ui/index.html`, OpenAPI `/v3/api-docs`에서 요청·응답 스키마를 확인한다. 표는 HTTP 메서드별로 센다.

| 메서드 | 경로 | 기능 |
| --- | --- | --- |
| GET | `/api/health` | 서버 상태 |
| GET | `/api/capabilities` | 기존 평가용 역량 사전·ID |
| GET | `/api/skill-categories` | 신규: 기술 10개·기타 묶음·저장 집계 |
| GET | `/api/postings` | 채용공고 목록·검색·진행/마감·페이지 |
| GET | `/api/postings/{postingId}` | 원문·이미지·현재 추출 상세 |
| GET | `/api/postings/{postingId}/skill-categories` | 신규: 현재 필수·우대 문장의 저장 분류 |
| GET | `/api/postings/{postingId}/fit?userId=...` | 공고 요구 역량과 기존 사용자 LV |
| GET | `/api/postings/{postingId}/capability-comparison` | 기존 역량 비교 |
| GET | `/api/postings/{postingId}/external-pass-materials` | 회사별 외부 합격자료 |
| GET | `/api/postings/{postingId}/external-pass-keywords` | 외부자료 기술 키워드 |
| GET | `/api/postings/{postingId}/recruit-units/{recruitUnitId}/comparison-candidates` | 비교 모집 단위 후보 |
| GET | `/api/postings/{postingId}/recruit-units/{recruitUnitId}/external-pass-collection-status` | 모집 단위별 수집 상태 |
| POST | `/api/users` | 사용자 생성 |
| GET | `/api/users/{userId}` | 사용자 조회 |
| POST | `/api/users/{userId}/projects` | GitHub URL·설명 PDF 프로젝트 등록 |
| GET | `/api/users/{userId}/projects` | 사용자 프로젝트 목록 |
| GET | `/api/users/{userId}/capabilities` | 사용자 기존 역량 평가 |
| GET | `/api/projects/{projectId}` | 프로젝트·기존 평가 상세 |
| PUT | `/api/projects/{projectId}/evaluations` | 기존 평가 결과 저장 |
| GET | `/api/projects/{projectId}/description-file` | 설명 PDF 다운로드 |

추가 query parameter와 검증 규칙은 OpenAPI가 기준이다. 이번 작업은 LV 산정 기준을 변경하지 않는다. 쓰기 작업은 실제 사용자·RDS 데이터에 검증 요청하지 않았다.

프론트 Next.js의 `/api/jobs`, `/api/skill-categories`는 브라우저용 중계 경로이고, Spring API와 별도로 실행되는 서버다. 로컬 연결은 `BACKEND_URL`을 사용한다. 채용공고를 제외한 사용자·성장·차트 등 프론트 전체가 Spring에 연결됐다는 의미는 아니다.

분류 상태, 최신 집계, 프론트와 배포 설정 범위는 [카테고리 API 계약](skill-category-api.md)을 참고한다.
