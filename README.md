# Capstone1

## 브랜치와 CI 규칙

- **브랜치**: `main` = 배포용(AWS), `develop` = 로컬용. 작업은 `feature/…` 브랜치에서 하고 PR로 합친다.
- **폴더**: 파트마다 맨 위 폴더 하나 — `job-skill/`(데이터 파이프라인), `backend/`, `frontend/`.
- **CI**(`.github/workflows/ci.yml`): `main`·`develop`으로 오는 PR마다 **바뀐 폴더의 시험만** 돈다. 시험이 통과해야 합친다.
- **새 폴더를 합칠 때**: 그 파트가 `ci.yml`에 자기 잡을 더한다(자리와 예시는 파일 안 주석). 잡 안의 명령(버전·빌드·시험)은 그 파트가 정한다.
