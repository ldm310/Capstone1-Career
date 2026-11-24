# 관리자 추출 검토

웹 `/admin`은 일반 회원에게 열리지 않는다. 계정의 RDS `career_lv_member.app_role`이 `ADMIN`인 경우에만 접근 가능하며, 메뉴도 관리자에게만 표시한다.

- 추출 검토: 회사/공고명/공고번호 검색, 상태별 조회, 실패 단계와 실패 횟수, 피드백 입력.
- 공지사항 관리: 기존 관리자 공지 작성·수정·삭제 화면.
- 넘기기(PASS): 해당 공고를 `SKIPPED`로 바꾸고 연결된 파이프라인의 자동 처리 대상에서 제외한다. 공고 자체를 삭제하지 않는다.
- 재추출 요청: 최소 5자 피드백을 저장하고 `RETRY_REQUESTED`로 전환한다. 즉시 OpenAI를 호출하지 않는다.
- 두 번의 실패가 기록되면 `OPEN` 상태에서 자동 재시도를 보류한다. SDK 내부 통신 재시도와 모집단위 확인용 추가 호출은 이 횟수와 다르다.
- 관리자 요청은 한 번만 점유하고, 피드백은 첫 추출과 모집단위 확인용 추가 호출에 함께 포함한다. 실패하면 검토 대기로, 성공하면 해결로 전환한다.
- 같은 요청을 둘이 처리하면 revision 검사로 뒤의 요청에 409를 반환한다. 모든 관리자 처리와 실행 결과를 이력 테이블에 남긴다.

## DB와 실행 연결

`db/migrations/008_extraction_review.sql`은 파이프라인 마이그레이션으로 적용한다. 웹의 `frontend/scripts/setup-community.mjs`도 같은 파일을 멱등 적용한다.

테이블:

| 테이블 | 역할 |
|---|---|
| `public.career_extraction_review` | 공고별 현재 상태, 실패 횟수, 최근 피드백, 실행 점유 정보 |
| `public.career_extraction_review_event` | PASS/RETRY/START/FAIL/RESOLVE 이력 |

웹은 기존 사용자용 RDS 연결을 사용한다. 실행 중인 파이프라인도 **같은 DB**에 연결하고 다음 환경 값을 지정해야 한다.

```env
CAREER_PIPELINE_NAMESPACE=staging
```

로컬 관리자 검토를 연결하려면 `local-review`를 사용한다. 웹은 이 변수가 없으면 `CAREER_PROFILE_NAMESPACE`를 사용한다. 파이프라인은 이 값이 없거나 `off`이면 기존 실행 방식을 유지한다. 운영 파이프라인의 실제 사용 namespace와 웹의 namespace를 일치시켜야 한다. 이 설정은 웹 배포만으로 노트북 Airflow에 전달되지 않는다.

파이프라인 환경 변경 후 해당 환경의 Airflow를 재시작하고 코드도 배포해야 한다. `step_collect`는 PASS/보류 공고를 제외하고 피드백 요청을 targets에 포함한다. `run_model`은 요청을 점유해 피드백을 적용하고 실행 결과를 DB에 기록한다. 이전 공고에 남아 있던 결과 파일도 명시적인 재추출 요청이 있으면 다시 처리한다.

웹 초기 설정은 성공한 추출 기록이 없는 실제 DB 공고를 `UNKNOWN`, 실패 횟수 0으로 등록한다. 기존 실패 횟수를 추정하지 않는다. 이미 저장된 관리자 판단은 초기 설정 재실행으로 덮어쓰지 않는다. 현재 UI는 **LLM 추출 실패와 미추출 공고 검토**를 대상으로 한다. OCR 전체 태스크나 DB 저장 단계의 모든 과거 장애를 복구해 채워 넣는 기능은 포함하지 않는다.

## 확인

```powershell
# 실제 RDS 테스트는 전용 테스트 계정/공고를 만들고 종료 시 정리한다.
$env:RUN_RDS_ADMIN_REVIEW_TESTS='1'
$env:PLAYWRIGHT_CHANNEL='msedge'
npx.cmd playwright test tests/admin-extraction-review.spec.ts
```

파이프라인 단위 테스트: `python -m pytest tests/test_extraction_review.py tests/test_pipeline_tasks.py -q`
DB 단위 테스트는 기존 규칙대로 로컬 임시 PostgreSQL만 사용하며, RDS에 임시 데이터베이스를 만들지 않는다.
