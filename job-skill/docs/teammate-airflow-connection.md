# 팀원 Airflow 연결 및 코드 배포

웹 → 기존 RDS 검토 대기열 → 팀원 Airflow 순서로 연결한다. Airflow REST API 계정이나 토큰을 웹에 저장할 필요가 없다.

## 실행 전에 확인할 것

- 저장소: `https://github.com/ldm310/Capstone1-Career`
- 배포 브랜치: `feature/admin-extraction-review` (main은 변경하지 않는다).
- Airflow가 읽는 기존 공고 RDS와 웹의 사용자 RDS가 같은 DB여야 한다. 코드의 대상은 `public.posting`, `public.extraction_run`이다. 예전 `job` 스키마 전용 코드에 이 파일 일부만 덮어쓰지 않는다.
- 이 버전은 Airflow 3.3.2, LocalExecutor, 기존 GPU OCR 구성을 기준으로 한다. 팀원의 실행 중인 DAG가 끝난 뒤 코드를 바꾼다.
- 기존 OPENAI_API_KEY, RDS 설정, OCR 설정은 유지한다. 값을 채팅이나 Git에 넣지 않는다.

## 팀원이 적용할 순서

1. 현재 체크아웃에서 변경 파일과 실행 중인 DAG를 확인한다. 매일 수집을 잠시 일시정지하고 진행 중인 실행이 끝난 뒤 배포한다. 일시정지 여부는 기록해서 배포 후 원래대로 복원한다.
2. 새 코드를 별도 체크아웃에서 확인하거나 기존 배포 절차로 `feature/admin-extraction-review` 커밋을 가져온다. 팀원 작업 파일에 강제 체크아웃하지 않는다.
3. 기존 Airflow `.env`에 `CAREER_PIPELINE_NAMESPACE=staging`을 추가한다. 도구를 사용할 경우:

```bash
python job-skill/configure_review_namespace.py --env-file /실제/Airflow/job-skill/.env --namespace staging
```

4. 기존 파이프라인 실행 환경에서 마이그레이션을 적용한다. 이미 Airflow 컨테이너가 있으면 다음과 같이 실행할 수 있다. `-f`에는 팀원의 실제 compose 경로를 넣는다.

```bash
docker compose -f /실제/Airflow/job-skill/docker-compose.airflow.yml exec -T airflow-scheduler python /opt/airflow/job-skill/db_load.py migrate
```

5. 기존 compose로 `up -d`하여 변경한 `.env`를 반영한다. 단순 `restart`는 변경한 env_file 값을 반영하지 않는다. 기존 GPU 이미지를 사용하며, Dockerfile/의존성을 바꾸지 않았다면 새 GPU 이미지 빌드는 필요 없다.

```bash
docker compose -f /실제/Airflow/job-skill/docker-compose.airflow.yml up -d
```

6. 연결과 DAG 불러오기를 확인한다. 이 명령들은 추출을 실행하지 않는다.

```bash
docker compose -f /실제/Airflow/job-skill/docker-compose.airflow.yml exec -T airflow-scheduler python /opt/airflow/job-skill/check_review_connection.py
docker compose -f /실제/Airflow/job-skill/docker-compose.airflow.yml exec -T airflow-scheduler airflow dags list-import-errors -o json
docker compose -f /실제/Airflow/job-skill/docker-compose.airflow.yml exec -T airflow-scheduler airflow dags list -o json
```

연결 점검은 `connected: true`, `namespace: staging`, `externalCalls: 0`과 상태별 건수를 출력해야 한다. 접속 비밀번호나 API 키는 출력하지 않는다.

7. 웹 배포 후 관리자 `/admin`에서 목록과 처리 상태를 확인한다. 매일 수집을 원래 활성 상태로 되돌리면 다음 실행이 요청을 처리한다. 연결 확인을 위해 `backfill_once`나 `daily_collect` 전체를 임의로 실행하지 않는다.

## 연결 후 동작

| 관리자 동작 | Airflow 동작 |
|---|---|
| 넘기기(PASS) | 연결된 namespace의 자동 추출 대상에서 제외 |
| 피드백을 남겨 재추출 요청 | 다음 수집 실행의 targets에 포함, 피드백을 LLM 입력에 추가 |
| 같은 공고가 2회 실패 | 추가 자동 추출 보류, 관리자 피드백 요청으로 다시 허용 |

실제 공고 재추출은 기존 OpenAI 연결을 사용하므로 비용이 발생한다. 연결 점검 명령 자체는 OpenAI를 부르지 않는다.

현재 로컬 관리자 화면은 기본적으로 `local-review`를 조회한다. 팀원 실행 결과를 로컬에서도 보려면 `frontend/.env.local`에 `CAREER_PIPELINE_NAMESPACE=staging`을 추가하고 웹 서버를 재시작한다. 회원/권한의 namespace는 기존 값을 유지한다.

## 되돌리기

문제가 생기면 DAG를 일시정지하고 직전 코드와 기존 `.env`를 복구한다. 새 테이블은 추가 구조라 삭제하지 않아도 된다. 대기 중 요청/관리자 피드백을 지우지 않는다.
