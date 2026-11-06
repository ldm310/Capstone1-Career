# RDS 채용공고 연결

공고 API는 수집 파이프라인이 매일 저장하는 RDS `career` DB의 `public` 테이블을 직접 조회한다. 복사·수동 import 없이 다음 요청에 새 공고가 반영된다.

```powershell
python deploy/backend/use_rds.py --env-file C:/Users/sol09/Carrer/career-team-db.env
```

설정 파일은 저장소 밖에 두며 `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`를 사용한다. 비밀번호를 명령행이나 저장소에 넣지 않는다. 실행 스크립트는 backend만 빌드·재생성하며 기존 로컬 DB 컨테이너와 볼륨은 유지한다. 이미 빌드한 이미지를 사용하려면 `--no-build`를 지정한다.

`compose.rds.yaml`은 기본 Compose 설정에 덮어쓰는 RDS 전용 설정이다. `docker,rds` 프로필, SSL 필수, 연결 풀 read-only 및 PostgreSQL 세션의 `default_transaction_read_only=on`을 적용한다. Hibernate DDL과 SQL 초기화는 비활성이다. 이 연결은 사용자/프로젝트 등의 쓰기 API 용도가 아니다.

조회 주소:

- `http://localhost:8080/api/postings?page=0&size=20`
- `http://localhost:8080/api/postings?status=진행&page=0&size=20`
- `http://localhost:8080/api/postings/{postingId}`
- `http://localhost:8080/api/capabilities`
- `http://localhost:8080/swagger-ui/index.html`

프론트는 `frontend/.env.local`의 `BACKEND_URL=http://localhost:8080`을 사용한다. 프론트의 기존 공고 어댑터는 진행 중인 최신 200개에서 데이터/백엔드 직무를 골라 표시하며 최대 5분 캐시한다. Spring 공고 API 자체는 다른 직무와 마감 공고도 조회할 수 있다.

현재 체크아웃처럼 `node_modules`가 저장소 루트에만 있으면 프론트 디렉터리에서 `npm run dev -- --webpack`으로 실행할 수 있다. 기본 Turbopack은 프론트 디렉터리 밖의 Next.js 패키지를 찾지 못하는 기존 환경 문제가 있다. 프론트 공고 API는 `http://localhost:3000/api/jobs?limit=4`에서 확인한다.

2026-11-06 확인 시 RDS에는 `public` 공고·추출·사전 테이블만 존재한다. `profile`, `external_data`가 없으므로 사용자·프로젝트·평가·합격자 비교·외부 합격자료 API는 이 연결에서 사용할 수 없다. 해당 기능을 운영하려면 별도 쓰기 연결·확장 테이블 및 권한 설계가 필요하다. 공고 연결 과정에서는 운영 DB의 스키마나 데이터를 변경하지 않는다.
