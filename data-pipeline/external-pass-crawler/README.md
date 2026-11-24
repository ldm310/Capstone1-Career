# 외부 합격자료 수집기

로컬 Docker에서 공개 합격자료를 수집해 기존 RDS에 저장한다. 기존 `job-skill` 파이프라인과 분리된 Python CLI다.

정책·DB 계약·일일 운영 방법은 [수집 문서](../../backend/docs/external-pass-collection.md), 실제 확인 결과는 [수집 검증](../../backend/docs/verification/external-pass-collection-verification.md)에 모았다.

공고 회사·직무 연결 전 원자료를 대량 확보하려면 [본문·이미지·대학 PDF 보관함](../../backend/docs/pass-evidence-archive.md)을 사용한다. 잡코리아·링커리어 본문과 검토한 대학 공식 수기집을 별도 로컬 보관함에 저장한다.

## 로컬 일일 수집

프로젝트 루트에서 비공개 env 파일을 전달한다. `DATABASE_URL` 또는 `EXTERNAL_DATABASE_URL`이 필요하며 비밀값은 커밋하지 않는다.

```powershell
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> build
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> migrate
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> scan
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> start
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> logs
```

- 매일 KST 09:00, 회사 최대 30곳, 회사당 2페이지·후보 40건, 최소 요청 간격 2초.
- 과거 공고를 포함한 진행 중 IT 공고에서 자료 누락·2건 미만·본문 누락을 스캔한다.
- 회사별 하루 한 번 확인하고, 본문·기술 요약·같은 회사 공고 연결을 함께 저장한다.
- 최소 표본은 2건이다. 비교 API는 동일 표준 직무의 자료만 센다.
- 본문은 별도 테이블의 추출 대기 상태로 보관하며 API·로그에 노출하지 않는다. 임베딩은 이후 단계다.
- PC와 Docker가 켜져 있어야 실행된다. 접근 차단은 자동 우회하지 않는다.

## 기존 회사 CLI와 비교 후보 배치

기존 CLI는 새 회사 작업을 수집하고 완료된 회사 자료를 재사용한다. 본문 저장·다음 날 재시도는 일일 CLI가 담당한다.

```powershell
# 이 디렉터리에서 Python 3.12 이상, requirements.txt 설치 후 실행
python -m external_pass_crawler --company-id 123 --dry-run
python -m external_pass_crawler --company-id 123
python -m external_pass_crawler.comparison_batch --target-posting-id 123 --target-recruit-unit-id 456 --dry-run
```

DB 연결은 명시적으로 주입하며 RDS 설정이나 .env를 자동 선택하지 않는다. 회사명은 법인 표기·공백·대소문자만 정규화하고, `--aliases-file`에 지정한 명칭만 추가로 허용한다. 타사·계열사·비IT·불명확한 직무는 제외한다.

## 검증

프로젝트 루트에서 아래 명령을 실행하면 새 임시 PostgreSQL 18에서 크롤러·Backend·HTTP 계약을 검증하고 테스트 DB를 제거한다. 실제 RDS 연결값은 읽지 않는다.

```powershell
python db/tests/verify_external_collection.py --owned-public --with-http-smoke --java-home <Java21경로>
```
