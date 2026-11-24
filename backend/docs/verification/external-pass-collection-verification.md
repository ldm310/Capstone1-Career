# 외부 합격자료 수집 검증

최종 운영 방향: 로컬 Docker의 링커리어 크롤러 → 기존 RDS 저장. 검증일은 2026-11-09(KST)이며 아래 실제 수집 수치는 당시 스냅샷이다.

## 실제 수집·API 확인

- RDS public-07 설치 후 public-08을 적용해 최소 표본 2건과 본문·회사 시도·일일 실행 기록을 추가했다. migration에서 기존 회사·공고·추출·사전 데이터의 전후 해시 일치를 확인했다.
- 카카오엔터프라이즈(회사 1721): 링커리어 자료 33159(backend), 23934(mobile)를 수집하고 공고 1721·1836에 연결했다. 본문 2건을 보완한 뒤 회사 상태 READY와 minimum_sample_size=2를 확인했다.
- 메가존클라우드(회사 83): 자료가 없던 대상에서 링커리어 자료 36734를 새로 수집했다. 1건이므로 회사 상태는 INSUFFICIENT다.
- 본문은 총 3건, 각각 1,479자·1,537자·3,812자이며 추출 상태 PENDING이다. 검증 결과에는 본문 대신 길이와 해시만 기록했다.
- 공고 1721의 자료·키워드 API는 모두 200, 자료 수와 키워드 출처 수는 2건이다. 본문은 API에 노출하지 않는다.
- 회사 전체 READY와 동일 직무 비교 READY는 구분한다. 서로 다른 직무 자료 두 건을 동일 직무 두 건으로 세지 않는다.
- 앞선 잡코리아 실험의 저장 자료는 별도 출처로 보존했지만 수집 코드는 링커리어만 유지한다. 이를 링커리어 수집 건수에 포함하지 않는다.

## 로컬 운영 확인

`capstone1-career-docker-external-pass-daily-1`이 비root·읽기 전용 파일시스템·restart policy unless-stopped로 실행됐다. 다음 실행은 2026-11-09 09:00 KST로 확인했다. PC와 Docker가 꺼져 있으면 정시 실행되지 않으며, 이후 시작 시 당일 누락 실행을 보완한다.

전체 스캔에서 미연결 자료가 있는 회사 1,141개를 확인했다. 하루 30개 회사 상한을 적용하고 나머지는 다음 날 순환한다. 영구 회사 시도 시각과 날짜별 실행 기록으로 중복 요청을 방지한다.

## 유지하는 회귀 검증

- public 신규 설치·반복 설치·최소 권한 설치와 pipeline 데이터 보존.
- 기존 5건 정책의 2건 전환, 직접/후보 비교의 1건·2건 경계.
- 과거 IT 공고 누락 스캔, 하루 중복 방지, 오전 9시 이전 대기, 일일 작업만 제한적으로 중단 복구.
- 회사·직무 검증, 출처 ID 충돌 rollback, stale worker 차단, 신규 공고의 기존 자료 재사용.
- 본문·요약·연결의 원자적 저장, 본문 해시 변경에 따른 추출 대기 상태, API·로그의 원문 비노출.
- robots·401/403/429·CAPTCHA 중단과 요청 간격.
- 실제 PostgreSQL에서 Backend 전체 및 HTTP 200/400/404/409 계약 검증.

GitHub Actions CI는 격리 PostgreSQL에서 위 검증을 수행한다. 실제 수집 일정은 Actions가 아니라 로컬 Docker가 담당한다.

문서·실험 코드 정리 후 크롤러 76개와 Backend 163개 테스트가 실패·오류·skip 없이 통과했다. HTTP 계약 검증과 웹 프로덕션 빌드도 성공했다.

## 재현

```powershell
python db/tests/verify_external_collection.py --owned-public --with-http-smoke --java-home <Java21경로>
```

실행기: [전체 검증](../../../db/tests/verify_external_collection.py), [HTTP smoke](../../../db/tests/smoke_external_collection_http.py), [일일 수집 테스트](../../../data-pipeline/external-pass-crawler/tests/test_daily.py). 실제 RDS 자격 증명 없이 임시 DB를 준비하고 종료 시 정리한다.

실환경 증거는 커밋하지 않는 `work/external-pass-daily-verification.json`에 보관한다. 초기 public-07·후보 출처 검증은 2026-11-08에 끝났으며, 당시 자료 0건이라는 결과는 위 실수집으로 갱신됐다. 운영 정책과 실행 명령은 [수집 문서](../external-pass-collection.md)에 모았다.
