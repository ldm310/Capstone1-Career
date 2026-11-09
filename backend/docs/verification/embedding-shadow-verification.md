# Embeddings SHADOW_MODE 검증

검증일: 2026-11-09. 브랜치: `feature/BE`. 정책: `keyword-mvp-2` 유지, 임베딩 관찰 정책 `semantic-shadow-v1`.

## 구현 결과

- Python 별도 배치: current IT 요건 조회 → 고정 전처리 → SHA-256 → 캐시 재사용 → 배열 요청 → index/차원 검증 → 신규 소유 테이블 저장.
- 기본 모델 `text-embedding-3-small`, 차원 1,536. 모델은 `OPENAI_EMBEDDING_MODEL`에서 설정한다. 키를 읽는 위치는 Python 실제 클라이언트의 `os.environ['OPENAI_API_KEY']`이며 설정 파일·JVM·명령 인자로 전달하지 않는다.
- 최대 64문장·8,192토큰/요청, 2,048토큰/문장. 기본 실행은 READ ONLY dry-run이다. 실제 생성은 `--apply`로 명시한다.
- 정상 캐시와 부분 성공 벡터를 보존한다. SDK 자동 재시도는 0회이며 FAILED/UNKNOWN은 기본 재실행에서 전송하지 않는다. 처리 여부를 알 수 없는 전송을 자동 반복하지 않는다.
- 기존 선정이 끝난 후보만 보강한다. tech ID·alias, 후보 선정, HIGH/LOW, 순위, 회사·공고 제한, 기존 점수는 임베딩을 참조하지 않는다.
- REQUIRED/PREFERRED/DUTIES를 독립 비교한다. 대상 요건별 최고 cosine의 평균이며 비교 문장이 없으면 null이다. `semanticMatchedRequirementCount`는 비교 가능한 대상 요건 수다. 임계값을 설정하지 않았다.

## RDS 확인과 적용

READ ONLY에서 pgvector 미설치를 재확인했다. 확장 설치는 시도하지 않았으며 `real[]`을 선택했다. 신규 소유 테이블 4개, 읽기 뷰 2개와 인덱스를 설치했다. 반복 migration은 정상적으로 이미 적용됨을 반환했다. 원본 public 테이블의 행 수·내용 해시를 설치 전후 비교해 동일함을 확인했다. 신규 테이블은 모두 실행 계정 소유다.

실제 저장된 벡터 0개, API 요청 이력 0개다. 테스트용 합성 벡터는 일회용 로컬 DB에만 넣었다.

구현된 전처리와 토큰 제한을 사용한 RDS dry-run:

| 항목 | 수 |
|---|---:|
| current IT 세 범주 요건 | 37,387 |
| 전처리 통과 요건 | 30,696 |
| 통과 REQUIRED / PREFERRED / DUTIES | 9,172 / 8,544 / 12,980 |
| 중복 제거한 미생성 입력 문장 | 26,274 |
| 토큰·개수 패킹 후 예상 요청 | 411 |
| 실제 OpenAI 호출 / 사용 토큰 | 0 / 0 |

제외: 회사명 포함 2,315, 활성 기술 없는 미분류 3,160, 직무 모호 1,022, 학력·태도 190, 개인정보 위험 1, 연수 제거 후 빈 문장 3행. 회사명 사전은 공고 회사 한 곳뿐 아니라 DB의 회사 이름 전체를 사용하므로 최초 설계용 예비 집계보다 보수적이다. 짧거나 일반적인 회사 이름은 기술 문장도 제외할 수 있으며 이 보수적 손실은 향후 전처리 검토 대상이다.

## 자동 검증

실제 OpenAI API를 호출하지 않고 아래 명령으로 실행했다. 부모 환경에 키가 있더라도 기본 테스트 자식 환경에서는 제거한다.

```sh
python db/tests/verify_external_collection.py --owned-public --with-http-smoke --java-home "$JAVA_HOME"
```

| 검증 | 결과 |
|---|---|
| 임베딩 Python | 18개 중 17개 성공, 실제 API smoke 1개 명시적으로 skip |
| 기존 크롤러 Python | 76개 성공, skip 없음 |
| 전체 BE | 174개 성공, 실패·오류·skip 없음 |
| Spring 실제 HTTP | 200/400/404/409와 SHADOW 필드 확인 |
| GET 전후 원본 데이터·시퀀스 | 동일 |
| migration·배치 전후 원본 행·시퀀스 | 동일 |
| 기존 실행 서비스 | 격리 검증 전후 동일 |
| 임시 DB | 검증 종료 후 제거 |

세부 검증:

- 동일 hash 재실행 시 추가 호출 0회, 여러 requirement가 같은 캐시 공유, 바뀐 요건 문장만 1개 재생성.
- 뒤집힌 응답 배열을 `data.index`로 매핑하며 누락·중복·범위 초과를 거부한다.
- 차원 오류, null, NaN, Infinity, 0 벡터, real[] float32 변환 후 0이 되는 벡터를 거부한다.
- 일부 벡터 실패 시 다른 성공 벡터 보존, 불확실 전송·프로세스 중단은 UNKNOWN으로 유지해 재호출하지 않음, 동시 실행 차단.
- 요청 중 원본이 바뀌면 오래된 벡터 연결을 하지 않는다.
- Python·Java가 같은 직무 fixture를 사용한다. 세 범주 분리·방향성 평균·null·부분/오래된/오류 상태를 검증했다.
- Java와 JavaScript의 semantic 벡터를 의도적으로 같게 줘도 기존 tech 교집합은 0이다.
- 후보의 semantic 점수가 기존 순서와 반대여도 추가 7개 필드를 제거한 전체 응답 JSON이 동일하다.
- 실제 PostgreSQL의 임베딩 SQL을 의도적으로 실패시켜도 REQUIRES_NEW 밖에서 오류가 흡수되고 원래 READ ONLY 트랜잭션의 SELECT가 정상 작동한다.
- Mock 예외에 비밀이 아닌 sentinel을 포함시켜도 안전한 코드만 반환한다. 코드·설정·fixture에 실제 API 키를 추가하지 않았다.

## 의미 정확도와 실제 생성

합성 fixture는 같은 의미/다른 표현, 수준 차이, 다른 역량, Java/JavaScript, Docker 사용/운영, 학습 예정/실제 구현의 6유형을 포함한다. Mock 벡터는 계산·저장·분리 동작 검증용이며 의미 정확도 증거가 아니다.

실제 API smoke는 실행하지 않았다. `RUN_OPENAI_EMBEDDING_SMOKE=1`일 때만 최대 합성 10문장·1회 요청하고 사용량, 설정한 가격, 추정 비용, 문장 쌍 점수를 기록한다. 가격 미설정 시 비용은 null이며 실제 청구액으로 해석하지 않는다. 실제 데이터 생성·의미 품질 검증·임계값 확정·순위 반영은 이번 검증에 포함되지 않는다. pgvector 경로는 현재 RDS에서 사용할 수 없어 real[] 경로를 실제 PostgreSQL로 검증했다.

실행 방법과 재실행 정책은 [배치 README](../../../data-pipeline/requirement-embeddings/README.md), 설계 계약은 [설계 문서](../embedding-shadow-mode.md)를 참고한다.
