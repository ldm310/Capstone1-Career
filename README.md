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
2. Settings → Actions → Runners → New self-hosted runner — 러너 두 대(토큰은 1시간이면 만료)
   - 노트북(Windows): 라벨 `career-laptop`, 서비스로 실행(사용자 계정 — Docker·git·py 를 씀) → 노트북 Airflow 배포
   - EC2(Linux, `ubuntu` 계정): 라벨 `career-ec2` → 웹 배포. 러너가 GitHub 에 일을 받으러 가서, 밖에서 EC2 로 SSH 를 열 필요가 없다
     ```bash
     mkdir -p ~/actions-runner && cd ~/actions-runner
     curl -o runner.tar.gz -L https://github.com/actions/runner/releases/download/v2.338.2/actions-runner-linux-x64-2.338.2.tar.gz
     tar xzf runner.tar.gz
     ./config.sh --url https://github.com/ldm310/Capstone1-Career --token <토큰> --name career-ec2 --labels career-ec2 --unattended
     sudo ./svc.sh install ubuntu && sudo ./svc.sh start
     ```
3. Settings → Branches: `main`·`develop`에 "PR 필수 + 검사 통과 필수"(검사: `changes`, `job-skill`, `job-skill-dags`)
4. Settings → Actions → General → Fork pull request workflows: **"Require approval for all external contributors"**
   — 공개 저장소라, 남이 PR 로 워크플로를 고쳐 우리 러너(노트북·EC2)에서 코드를 돌리지 못하게 한다

EC2 스테이징 주소는 처음 한 번 만든다(여러 번 해도 안전, 운영은 건드리지 않음):
`ssh -i <키> ubuntu@15.164.137.78 'bash -s' < deploy/web/setup_ec2.sh` (2026-11-03 해 둠)
