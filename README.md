# Capstone1

## 브랜치와 CI 규칙

- **브랜치**: `main` = 배포용(AWS), `develop` = 로컬용. 작업은 `feature/…` 브랜치에서 하고 PR로 합친다.
- **폴더**: 파트마다 맨 위 폴더 하나 — `job-skill/`(데이터 파이프라인), `backend/`, `frontend/`.
- **CI**(`.github/workflows/ci.yml`): `main`·`develop`으로 오는 PR마다 **바뀐 폴더의 시험만** 돈다. 시험이 통과해야 합친다.
- **CD**(`.github/workflows/cd.yml`): 합쳐지면 바뀐 파트만 배포한다. `develop` → `main` PR은 배포할 때 사람이 올린다.
  - `develop` → 웹 **스테이징**(EC2 3001번, https://staging.15-164-137-78.sslip.io, 시험용 데이터)
  - `main` → 웹 **운영**(EC2 3000번, https://15-164-137-78.sslip.io) + `job-skill`(RDS 마이그레이션 → 노트북 Airflow)
  - 웹 배포(`deploy/web/deploy.sh`)는 판마다 따로 빌드한 뒤 한 번에 바꾸고, 안 뜨면 이전 판으로 되돌린다. 그 커밋에 `frontend/`가 없으면 웹을 건드리지 않는다.
- **설정은 `.env`**: 주소·비밀번호·포트처럼 환경마다 다른 값은 코드에 넣지 않고 각 폴더의 `.env`에서 읽는다(`.env`가 로컬/운영 스위치).
- **새 폴더를 합칠 때**: 그 파트가 `ci.yml`에 자기 잡을 더한다(자리와 예시는 파일 안 주석). 잡 안의 명령(버전·빌드·시험)은 그 파트가 정한다.

## 관리자 설정 (저장소 주인 `ldm310`, 한 번)

1. Settings → Secrets and variables → Actions → Secrets
   - `RDS_HOST`, `RDS_PASSWORD`: RDS 주소와 마스터 암호(job-skill 마이그레이션)
   - `EC2_SSH_KEY`: EC2(`ubuntu@15.164.137.78`)에 들어가는 개인 키 전체. 배포 전용 키를 새로 만들어 쓰는 것을 권한다
     (`ssh-keygen -t ed25519 -f career-deploy -N ""` → `career-deploy.pub` 한 줄을 EC2 `~/.ssh/authorized_keys`에 추가 → `career-deploy` 내용을 Secret 에).
2. Settings → Actions → Runners → New self-hosted runner(Windows)를 노트북에 설치, 라벨 `career-laptop`, 서비스로 실행
3. Settings → Branches: `main`·`develop`에 "PR 필수 + 검사 통과 필수"(검사: `changes`, `job-skill`, `job-skill-dags`)

EC2 스테이징 주소는 처음 한 번 만든다(여러 번 해도 안전, 운영은 건드리지 않음):
`ssh -i <키> ubuntu@15.164.137.78 'bash -s' < deploy/web/setup_ec2.sh`
