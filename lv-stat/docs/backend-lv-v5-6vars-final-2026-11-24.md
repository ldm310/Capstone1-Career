# 백엔드 LV 기준 v5 최종 — 6변수 (신입 · 작은 프로젝트 기준) (2026-11-24)

> v4(7변수, `backend-lv-v4-7vars-final-2026-11-21.md`)를 대체. 검토: v4까지 백엔드 10년차 점검자 · 백엔드 팀장(면접관) 에이전트 통과.
> 그 뒤 사용자 결정으로 바꾼 것(에이전트 재검토 전): '기본'도 1점 · 단계 구간표 대신 점수 비율 · 가중치 없이 단순 평균 · 레포를 합쳐서 판정 · 모름 변수는 평균에서 뺌 · 기술 기록(T/F) 추가 · 웹 서버 변수 삭제(배포한 레포의 77%에 웹 서버 설정이 없음, `webserver-evidence-survey-2026-11-24.md`) · DB는 데이터베이스 카테고리의 깊이, 배포는 운영 배포 카테고리 LV를 씀 · 부가 기술 영역 수 가점.
> 다른 카테고리와 공통인 계산 규칙은 `lv-calc-7categories-2026-11-24.md`. 항목 점수 · 단계 시작값은 임시값이며 8명 테스트로 맞춤.

## 공통 규칙
1. 백엔드 레포: 서버 프레임워크로 만든 API 1개 이상이 DB까지 이어짐 + 내 백엔드 코드 50줄 이상(빈 줄 · 주석 · 자동 생성 파일(gradlew · mvnw · lock 파일 · 자동 생성 마이그레이션) 제외). 이런 레포만 합쳐서 판정하고, 하나도 없으면 백엔드 LV 0. 빈 레포 · 템플릿만 거르는 문턱이라 일부러 낮게 둠(높이면 같은 기능도 줄 수가 많은 스택이 유리).
2. 변수 LV = 받은 점수(기본 포함) ÷ 만점 × 5 → 0.0~5.0, 소수 첫째 자리 표시(예: 7/9점 → 3.9). 만점으로 나누는 건 변수마다 만점이 달라서(5·8·9). '기본'은 다른 항목과 같은 1점 항목(선행 조건 아님). 상한(최대 1·2)은 변수 LV의 최댓값.
3. 수량: 표시 없는 항목은 1곳 이상. 비율은 분모·분자 모두 내 코드. '절반 이상' 항목은 대상이 1~2개면 전부 충족해야 점수.
4. 해당 없음: 대상이 0개인 1점 항목만 만점에서 뺌(목록 API 0개, 외부 서비스 호출 0개). 2점 항목은 해당 없음 없이 0점.
5. 가점형 항목: 캐시 · 백그라운드 작업은 제대로 했을 때만 점수와 만점에 함께 넣음. 안 쓰거나 틀리면 계산에서 뺌.
6. 작동하는 것만 인정: 선언만 있고 연결이 없으면 0점(활성화 설정 없는 어노테이션, verify 없는 JWT, 라이브러리 기본값만 있는 타임아웃 등).
7. 겹침 금지는 두 경우만: 401·403 단언 → 보안 테스트만, 환경 변수 → 비밀값 숨기기만.
8. 테스트: 결과를 단언하는 내 테스트만. 자동 생성 테스트(`contextLoads`, `toBeDefined`뿐인 spec) 제외.
9. 팀 레포: '있는지'만 보는 기본 항목(로그인 기능 · 로깅 라이브러리)은 레포 단위, 실질 API · 저장 · 조회는 내 줄. 그 변수에서 내 줄로 받은 점수가 하나도 없으면 그 변수 LV는 0. 분모 · 분자 · 상한은 내 줄. 공용 설정 파일(보안 · 로그 설정 등)은 내 줄 과반일 때만.
10. 운영 설정 = 배포 근거(Dockerfile CMD · compose · 배포 스크립트 · prod 프로필)가 실제로 읽는 설정과 실행 명령. 프로필이 하나뿐이면 그 설정. 배포 근거가 없으면 운영 상한 적용 안 함.
11. 근거는 코드 · 설정 파일 · 배포 스크립트만. README · 문서의 주장은 점수로 안 치고 'README 주장만 있음'으로 표시.
12. 0점과 모름: 0점 = 기능을 안 만든 경우 등. PaaS가 대신 처리해 근거가 없는 것도 점수 없음('PaaS 대행' 표시). 모름 = 탐지 규칙이 없는 스택 → 모름 변수는 평균에서 빼고 '일부 모름' 표시, 모든 변수가 모름이면 LV '판정 불가'.
13. [AI 확인]: 통과 · 거절 각각 사람 판정과 90% 이상 일치한 항목만 쓰고, 미달이면 만점에서 뺌. 모름 = 0점. (예외: 공통 처리는 규칙으로 판정하고, 승인된 검증기의 '거절'만 0점으로 반영. 모름 · 승인 전이면 규칙 판정 그대로)
14. 레포 합치기: 백엔드 레포를 모두 합쳐 한 번에 판정. 항목마다 모든 레포 중 가장 좋은 결과를 쓰고 같은 항목은 한 번만 셈. 한 항목의 조건은 한 레포 안에서 채워야 함(조건을 레포끼리 섞지 않음). 단, 개수 · 비율(API 5개, '절반 이상')은 모든 레포의 대상을 합쳐서 셈. 상한 실수가 있는 레포는 그 변수 계산에서 빼고, 모든 레포에 그 실수가 있으면 상한 적용.
15. 백엔드 LV = (로그인·보안 + WAS + API + 로그 + DB + 배포) ÷ 6, 가중치 없음, 소수 첫째 자리. DB = 데이터베이스 카테고리의 깊이(0~5), 배포 = 운영 배포 카테고리 LV(0~5). 부가 기술 영역 수는 단계로 바꿔 평균을 올릴 때만 넣음. 6변수 LV를 항상 같이 표시.
16. 스택 공정성: '무엇을 했는지'로만 판정. Spring Boot가 아니어도 같은 일을 했으면 같은 점수.
17. LV 밖: 기술 이름 → 아래 '기술 기록'(T/F, 공고 대조). 역할 나누기 · 테스트 품질 → 코드 품질.

## 1. 로그인·보안 (만점 9)

| 할 일 | 판정 기준 | 점수 |
|---|---|---|
| 기본 | 회원가입·로그인 + 가입 때 비밀번호를 느린 해시(BCrypt·Argon2·PBKDF2)로 저장. 소셜 로그인만이면 서버가 제공자 토큰을 확인하고 자체 토큰·세션 발급 | 1 |
| 접근 막기 | 쓰기 API 전부(가입·로그인 제외)에 인증 확인(서명 검증 포함) | 1 |
| 권한 나누기 | 역할(관리자·일반)별 접근 제한이 작동하게 연결 | 1 |
| 본인 확인 [AI 확인] | 수정·삭제 API의 절반 이상에서 작성자 = 로그인 사용자 확인 | 2 |
| 토큰·세션 수명 | 만료 + 재발급(또는 세션 만료)과 로그아웃 무효화 둘 다 | 1 |
| 비밀값 숨기기 | 비밀번호·키가 코드·커밋 기록에 없음(환경 변수·CI secret, .env는 gitignore) | 1 |
| 보안 테스트 | 401·403·남의 글 수정 거부를 각각 단언 (일부만이면 1점) | 2 |

상한: SQL에 사용자 입력을 문자열로 이어 붙임 → 최대 1 / 비밀번호를 평문으로 저장 → 최대 1 / 쿠키로 인증하면서 CORS 자격 증명 허용 + 모든 출처 → 최대 2

## 2. WAS (만점 5, 백그라운드 작업을 제대로 하면 6)

| 할 일 | 판정 기준 | 점수 |
|---|---|---|
| 기본 | 백엔드 레포 기준(공통 규칙 1) 충족 | 1 |
| 설정 나누기 | 개발·운영 설정을 따로 둠 | 1 |
| 운영 실행 | 배포 근거의 실행 명령이 운영 설정·운영 모드로 백엔드 서버를 띄움 | 1 |
| 백그라운드 작업 (가점형) | 정해진 시간 실행 또는 오래 걸리는 일을 따로 처리(작동 연결 포함) + 실패 처리는 내 코드(try/catch 로그·재시도 설정) | 1 |
| 공통 처리 | 요청 흐름에 끼우는 직접 만든 코드 중 서로 다른 목적 2종, 각각 API 3개 이상에 적용. 제외: 인증·인가·로그인 사용자 주입·입력 검사·요청 로그·추적 ID·전역 예외·DB 세션 주입·CORS·프레임워크 내장 기능. 규칙으로 판정하고, 승인된 AI 검증기가 '중복 코드를 대신하지 않음'으로 거절하면 0점 | 2 |

상한: 운영 설정에서 DEBUG 켬 · 오류 응답에 스택 노출 · 개발 서버로 실행 → 최대 2

## 3. API · 외부 API · 캐시 (만점 9 — 외부 API를 안 쓰면 8, 캐시를 제대로 하면 +1)

| 할 일 | 판정 기준 | 점수 |
|---|---|---|
| 기본 | 내 실질 API 5개 이상(헬스 체크·자동 생성 API 제외) | 1 |
| 주소 규칙 (절반 이상) | 주소는 명사, 하는 일은 HTTP 메서드로 구분 | 1 |
| 입력 검사 (절반 이상) | 입력 받는 API(파일 업로드 포함)에 길이·범위·형식·크기 검사가 작동하게 연결 | 1 |
| 필요한 값만 응답 (절반 이상) | DB 모델을 그대로 반환하지 않고 응답 모양을 따로 정함 | 1 |
| 오류 응답 통일 | 전역 예외 처리로 같은 모양 + 알맞은 상태 코드 2종 이상 | 1 |
| 목록 나눠 보내기 (절반 이상) | 목록 API에 페이지네이션 | 1 |
| 외부 API (절반 이상) | 외부 서비스(결제·메일·지도·AI·파일 저장소)를 부르는 곳에 직접 설정한 타임아웃 + 실패 처리(오류 응답·재시도) | 1 |
| 캐시 (가점형) | 만료 시간 + 우리 DB 데이터면 바뀔 때 삭제(외부 응답 캐시는 만료 시간만) + 작동 연결 | 1 |
| 테스트 | 실질 API의 절반 이상을 내 테스트(API 테스트 또는 그 API가 부르는 서비스 테스트)가 다룸 | 2 |

상한: 비밀번호(해시 포함)가 응답에 나감 → 최대 2

## 4. 로그 (만점 8)

| 할 일 | 판정 기준 | 점수 |
|---|---|---|
| 기본 | print·console.log 대신 로깅 라이브러리 사용 | 1 |
| 예외 로그 | 빈 catch 0개 + 특정 예외만 골라 처리하고 나머지는 원인 보존 재던짐 또는 스택 로그 + 전역 처리기가 500을 스택과 함께 error 로그 | 1 |
| 요청 로그 | 요청마다 경로·상태 코드·처리 시간을 미들웨어·필터 한 곳에서 기록 | 1 |
| 로그 설정 | 운영 로그 레벨 + 보관(파일·보관 기간, 또는 stdout + 로그 드라이버) | 1 |
| 요청 추적 ID | 요청마다 ID를 붙여 그 요청의 모든 로그에 남김 | 2 |
| 원인 찾은 기록 [AI 확인] | 버그 수정 커밋에 원인 + 같은 커밋·PR에 회귀 테스트 | 2 |

상한: 비밀번호·토큰을 로그에 남김 → 최대 2

## 5. DB → 데이터베이스 카테고리의 '깊이'를 씀
한 것 중 가장 높은 단계(1 연결 · 2 테이블 설계 · 3 인덱스 · 4 트랜잭션 · 5 쿼리 튜닝). 판정은 데이터베이스 카테고리 기준을 따름.

## 6. 배포 → 운영 배포 카테고리 LV를 씀
배포한 레포 수 · 평균 기간(Actions 방식). 판정은 운영 배포 카테고리 기준을 따름.

## 부가 기술 영역 (가점)
- 파일 저장소(S3 등) · 실시간 통신(WebSocket 등) · API 문서(Swagger 등) · 소셜 로그인(카카오·구글 등) 중 몇 영역을 썼는지 → 단계 → 평균을 올릴 때만 넣음.
- 캐시는 API 변수의 캐시 가점에서 세므로 여기서는 뺌(중복은 한 번만).
- 썼다고 보는 기준은 아래 기술 기록의 T 조건과 같음. 기술 이름이 아니라 영역으로 세서 스택끼리 공정하게 봄.

## 기술 기록 (LV 밖 · T/F · 모든 카테고리 공통)
점수에는 안 넣고, 공고에 기술 이름이 나오면 대조. 기술 이름은 팀 사전 이름으로 통일.

| 구분 | T 조건 |
|---|---|
| 프레임워크(서버·화면 뼈대) | 그 프레임워크로 게이트를 통과한 레포가 있음. 서버 = 그걸로 만든 API가 DB까지 이어짐 + 내 코드 50줄 이상. 화면 = 화면 1개 이상 + 내 UI 코드 50줄 이상 |
| 그 밖의 기술(JPA·JUnit·Redis·S3 등) | 내 코드에서 실제로 호출한 곳 1곳 이상, 또는 설정 파일에 그 기능이 쓰이도록 적혀 있음(주석·끄는 값·예시 파일이면 F) |
| F | 의존성 파일이나 import 줄에만 있음 |

| 변수 | 기록할 기술 (예시) |
|---|---|
| 로그인·보안 | Spring Security · Passport · JWT 라이브러리 · 소셜 로그인(카카오·구글) |
| 웹 서버 (변수는 삭제, 기록만) | Nginx · Apache · Caddy · Traefik |
| WAS | Spring Boot · NestJS · Express · Django · FastAPI · Celery |
| API | Swagger · WebSocket · Redis(캐시) · 외부 API(S3·결제·메일) |
| 로그 | Logback · winston · pino |
| DB | MySQL · PostgreSQL · MongoDB · JPA · MyBatis · Prisma |
| 배포 | Docker · docker-compose · GitHub Actions · AWS EC2 |

- 공고 문장 = 기술 T/F + 관련 변수 항목. 예: "Redis로 캐시 구현" = Redis T + 캐시 항목 통과. "JPA 사용 경험" = JPA T.
- 기술 이름이 붙은 문장은 그 기술을 쓴 레포의 근거만 봄(예: Django 레포의 N+1 해결은 "JPA로 N+1 해결"에 안 침).

## WAS·API별 탐지 예시

| 판정 대상 | Spring Boot | NestJS·Express | Django·DRF | FastAPI |
|---|---|---|---|---|
| 설정 나누기 | `application-{dev,prod}` | `.env.*` · ConfigModule | settings 분리 · django-environ | `BaseSettings` · `.env.*` |
| 운영 실행 | `SPRING_PROFILES_ACTIVE=prod`로 jar 실행 | `NODE_ENV=production` + node·PM2 | gunicorn + 운영 settings | gunicorn·uvicorn(`--reload` 없이) + 운영 설정 |
| 백그라운드 | `@Scheduled`·`@Async` + `@EnableScheduling`·`@EnableAsync` | `@nestjs/schedule` · BullMQ · node-cron | Celery · Celery beat | BackgroundTasks · Celery · APScheduler |
| 공통 처리 | Filter · Interceptor · AOP | Interceptor · Pipe · 미들웨어 | 미들웨어 · 데코레이터 | 미들웨어 · Depends |
| 운영 상한 | `include-stacktrace: always` | 개발 모드 에러 응답 · nodemon | `DEBUG=True` · runserver | `--reload` · `debug=True` |
| 접근 막기·권한 | SecurityFilterChain · `@PreAuthorize` + `@EnableMethodSecurity` | 가드 등록 · 인증 미들웨어 | `permission_classes` | `Depends(현재 사용자)` |
| 입력 검사 | `@Valid` + 제약 | class-validator + `ValidationPipe` · zod · Joi | serializer 검증 | Pydantic 제약 |
| 응답 모양 | 응답 DTO | 필드를 골라 새 객체로 | serializer `fields` 명시(`__all__` X) | `response_model` |
| 오류 응답 통일 | `@RestControllerAdvice` | `ExceptionFilter` · 에러 미들웨어 | `EXCEPTION_HANDLER` | `exception_handler` |
| 페이지네이션 | `Pageable` | `skip`/`take` · `limit`/`offset` | `pagination_class` | `limit`/`offset` |
| 외부 API 타임아웃 | RestTemplate·RestClient·WebClient·OpenFeign에 직접 설정 | axios `timeout` · AbortSignal | requests `timeout=` | httpx `timeout` 직접 지정 |
| 캐시 | `@Cacheable`·`@CacheEvict` + `@EnableCaching` + TTL 캐시(Caffeine·Redis) | cache-manager·ioredis TTL + 삭제 | `cache.set(timeout)` + `delete` | Redis `setex` + 삭제 · fastapi-cache |
| 로거·추적 ID | SLF4J · MDC | Logger·winston·pino · AsyncLocalStorage | `logging` · `contextvars` | `logging` · `contextvars` |
| 테스트 | JUnit · MockMvc | Jest · supertest | pytest-django · `APITestCase` | pytest · `TestClient` |

## DB·ORM별 탐지 예시 (참고: 깊이 4 트랜잭션 · 5 쿼리 튜닝, 로그인·보안 SQL 상한)

| 판정 대상 | JPA | MyBatis | TypeORM·Sequelize | Prisma | Django ORM | SQLAlchemy |
|---|---|---|---|---|---|---|
| 트랜잭션 | `@Transactional` | `@Transactional` | `transaction()` 안에서 manager·t로 씀 | `$transaction` · 중첩 쓰기 | `transaction.atomic` | 단일 commit · `session.begin()` |
| N+1 해결 | fetch join · `@EntityGraph` · `@BatchSize` | select 속성 없는 조인 매핑 | `relations` · `leftJoinAndSelect` · `include` | 목록 API에서 행마다 쿼리 없음으로 판정 | `select_related` · `prefetch_related` | `joinedload` · `selectinload` |
| SQL 상한 | 문자열 이어 붙인 JPQL·native | `${}` | 문자열 이어 붙인 `query()` | `$queryRawUnsafe` · `$executeRawUnsafe` | 문자열 포맷한 `raw()`·`extra()` | f-string을 넣은 `text()` |

## 공개 레포 시험
- (11-21, 4개) Spring Boot · Django · FastAPI · NestJS 레포 모두 항목별 근거가 같은 뜻으로 대응됨. 신입 과제 레포에서도 요청 추적 ID를 붙인 사례 확인 → 2점 항목이 신입에게 가능한 수준.
- (11-24, 26개) 배포한 백엔드 레포 중 웹 서버 설정이 레포에 있는 건 23% → 웹 서버 변수 삭제(`webserver-evidence-survey-2026-11-24.md`).

## 다음에 확인할 것
- 8명 테스트로 항목 점수 · 단계 시작값 맞추기. 인프라를 안 맡은 팀원도 넣기.
- 같은 명세를 여러 스택으로 만든 RealWorld(Conduit) 구현체 3~4개로 변수별 LV가 같게 나오는지 확인(스택 공정성 시험).
