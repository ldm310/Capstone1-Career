# Requirement embeddings: SHADOW_MODE

기존 키워드 후보를 유지하고 임베딩 유사도만 응답에 추가한다. API 요청 중에는 OpenAI를 호출하지 않는다. Python 배치만 `OPENAI_API_KEY` 환경변수를 읽는다. 실제 키를 파일·명령 인자·로그에 넣지 않는다.

## 실행

Python 3.12 이상에서 이 디렉터리를 작업 경로로 사용한다.

```sh
python -m pip install -r requirements.txt
python -m requirement_embeddings.migrate --inspect
python -m requirement_embeddings
python -m requirement_embeddings.migrate
python -m requirement_embeddings --apply
```

`DATABASE_URL`은 실행 환경에 주입한다. `--inspect`는 READ ONLY로 확장 설치·권한을 확인한다. 확장을 설치하지 않는다. 이미 사용 가능한 vector가 있으면 vector, 없으면 real[]을 선택한다. 기본 배치는 READ ONLY dry-run이며 키나 OpenAI 호출 없이 입력·중복·예상 요청 수를 집계한다. `migrate`만 신규 `public.be_*` 소유 객체를 설치하며 원본 테이블을 변경하지 않는다. migration 09 SQL은 전용 실행기가 타입을 결정하는 템플릿이므로 직접 psql로 실행하지 않는다.

`--apply`는 명시적인 실제 생성·저장이다. 기본 최대 100,000행을 확인하며 `--limit N`으로 줄일 수 있다. 제한에 걸리면 `limited=true`다. 작은 limit은 requirement_id 앞부분만 처리하므로 전체 처리 시 충분히 크게 지정한다. 최대 64문장·8,192토큰/요청, 2,048토큰/문장으로 제한한다.

| 환경변수 | 기본값 / 의미 |
|---|---|
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `OPENAI_EMBEDDING_DIMENSIONS` | `1536`, Python과 BE 동일하게 설정 |
| `OPENAI_API_KEY` | Python 실제 생성 시에만 필요 |
| `POSTING_EMBEDDING_MODE` | BE `SHADOW_MODE`, 비활성화는 `OFF` |
| `EMBEDDING_PRICE_PER_MILLION_TOKENS` | 선택: 확인한 백만 입력 토큰당 USD. 미설정 시 비용 `null` |

설정 버전 `embedding-config-v1`, 전처리 `requirement-input-v1`, 비교 `semantic-shadow-v1`을 사용한다. 변경된 모델·차원·버전은 기존 캐시와 분리한다. source fingerprint·직무 사전 해시·current run이 다르면 오래된 벡터를 비교하지 않는다.

## 재실행과 실패

모델/구성/전처리/hash의 유일 제약과 전역 advisory lock으로 중복 저장·동시 생성 요청을 차단한다. 동일 입력은 READY 캐시를 공유하며 바뀐 문장만 새 요청 대상이다. 부분 실패 시 성공 데이터는 보존한다. 오류는 고정 코드만 기록한다.

SDK 자동 재시도는 0회다. FAILED와 UNKNOWN은 기본 재실행에서 보내지 않는다. 중단된 IN_FLIGHT는 UNKNOWN으로 전환한다. 전송 후 DB 저장 전 장애에서는 공급자 처리 여부를 확정할 수 없어 자동 재전송을 하지 않는다. 재시도 명령은 제공하지 않으며 요청 이력을 확인한 별도 운영 조치가 필요하다. 기존 벡터를 전체 삭제해서 다시 생성하지 않는다.

## 검증

```sh
python -B -m unittest discover -s tests -v
# 저장소 루트: 일회용 PostgreSQL + Python + Java + HTTP 전체 검증
python db/tests/verify_external_collection.py --owned-public --with-http-smoke --java-home "$JAVA_HOME"
```

DB 테스트는 실행기가 만든 loopback `extcrawler_test_embedding_*`에서만 실행한다. 전체 실행기는 상위 환경에 키가 있어도 자식 기본 테스트에서 제거한다. Mock 테스트는 의미 정확도나 임계값을 검증하는 테스트가 아니다.

`tests/fixtures/benchmark-pairs.json`에는 비식별 합성 6유형이 있다. 실제 smoke는 `RUN_OPENAI_EMBEDDING_SMOKE=1`을 명시할 때만 최대 10문장·1회 요청한다. 사용량·확인한 가격·추정 비용·문장 쌍 점수는 무시되는 `work/embedding-shadow-real-smoke.json`에 저장한다. 가격을 설정하지 않으면 추정 비용은 null이다. 6유형 중 첫 5쌍만 실제 smoke 대상이며 기본 테스트는 skip한다. 임계값·HIGH/LOW·순위 적용은 구현하지 않는다.

설계와 검증 결과: [embedding-shadow-mode.md](../../backend/docs/embedding-shadow-mode.md).
