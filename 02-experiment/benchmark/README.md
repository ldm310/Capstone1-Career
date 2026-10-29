# 20명 A~E 벤치마크 연결

독립 Python 실행기. 보관한 50/100명 코드 import 없음. 기준은 사용자가 제공한 RUBRIC_SOURCE.md와 31개 조건이며 draft다. 기존 6개 RAG 조건과 다르다. 사용자 자료·Git 이력은 변경하지 않는다.

## 구성

| A | AST에서 구현 추출, 로그/현재 코드·테스트 해시 연결 검사 → 공통 규칙 |
| B | 전체 원문·기준표 → LLM 조건·LV 직접 반환 (인용 오류는 표시만, LV를 대체하지 않음) |
| C | LLM 조건별 해석 → 인용 검사 → 규칙 |
| D | C와 동일 추출 응답 → 전체 조건·기여·위험을 별도 LLM이 원문 재검토 → 규칙 |
| E | C와 동일 추출 응답 → 사전 위험 규칙으로 선택된 조건만 검토/병합 → 규칙 |

모두 고정 워크플로이며 탐색 Agent/Multi-agent나 LangGraph 실험이 아니다. 모델의 파일 도구/실행 도구는 없다. C 추출 결과는 D/E와 공유; D/E 검토 응답은 서로 공유하지 않는다. 공통 호출은 논리 비용/시간에서 각 후보에 귀속하고 물리 원장은 한 번만 기록한다.

조건부 적용은 8개 위험의 yes/no/unknown과 근거를 기록한다. 없는 인용 또는 근거 없는 면제는 unknown으로 되돌린다. 위험 적용이 불명확하면 L2 이상은 보류한다. 위험별 직무 세부 검증 항목의 기계 판정은 아직 완성된 정책이 아니라 L2 해석 프롬프트 수준이다. 사람 검토 후 확정해야 하며 모형이 임의 면제하지 않는지 평가가 필요하다.

## 입력 범위와 안전

users20.json에 등록된 사용자별 파일만 읽는다. current commit Git blob과 작업 파일 hash를 대조한다. PDF를 pypdf로 추출하고 file#page=N으로 인용한다. 문서의 명령은 신뢰하지 않는다. 모든 방식에 동일 원문과 자동 추출 fact를 준다. 각 결과에 provided_files를 저장하지만 모델이 실제로 주의 깊게 읽었음을 입증하지는 않는다.

review_only/design.json은 집계용 split만 사용하며 프롬프트에 넣지 않는다. 생성 의도/정답/다른 사용자/평가 결과 접근 금지. 기준 답안 파일을 읽는 자동 정확도 집계기는 아직 연결하지 않았다. 사람이 검토한 답안이 없으므로 품질 수치는 N/A다.

인용 존재 검사와 의미 검증은 다르다. matched quote로 met을 자동 만들지 않는다. 개인 기여 gate가 미확인이면 최종 LV는 근거 부족. 합성 작성자 이력을 실제 인물의 기여로 인정하지 않는다. 누적 L3 실제 활용 조건 때문에 현 자료는 상위 긍정 사례가 부족하다.

## 모드 및 명령

현재 환경 Python 3.13.15 / requirements.txt 버전 사용. 루트 격리 .venv에 pypdf만 추가했다. 원격 의존성이나 FE 설치 변경은 없다.

```bash
cd /Users/idongmin/Desktop/experiments/lv-evaluation/career-mock20-v1
../.venv/bin/python -m pytest test_dataset.py benchmark/test_bench.py -q
../.venv/bin/python benchmark/bench.py --mode mock --output benchmark/runs/mock
../.venv/bin/python benchmark/bench.py --mode replay --replay-source benchmark/runs/mock --output benchmark/runs/replay
```

동일 명령 재실행은 성공 슬롯과 정상 응답을 재사용한다. 결과/응답은 append+fsync. 동시에 같은 출력 폴더를 실행하지 못하도록 파일 잠금. manifest가 바뀌면 덮어쓰지 않고 중단한다. 새 기준/코드/모델은 새 출력 폴더를 사용한다. 실패 원장을 보존하지만 실패 후 재시도는 사용자가 명령을 재실행할 때만 한다. 429/인증/파싱 오류에서 중단하며 모델·계정·유료 API fallback 없음. 공급자 응답 직후 프로세스 종료의 exactly-once는 보장하지 않는다.

mock은 가짜 인용과 B의 LV5를 일부러 반환해 직접 판정 보존 및 검토 경로를 시험한다. 이 결과는 모델 품질이 아니다. replay는 동일 입력 해시와 프롬프트/모델/코드의 저장 응답만 재생하며 캐시 누락 시 실패한다. mock replay는 실제 모델 응답 replay가 아니다.

## Live 준비 (이번 작업에서 실행하지 않음)

CLIProxyAPI 설정의 localhost와 기존 access key를 읽고 OpenAI 공식 SDK로 호출한다. OAuth credential 파일은 읽지 않는다. 프록시가 같은 모델·출력 형식 기능을 제공한다는 보장은 없으므로 JSON schema를 프롬프트에 넣고 Pydantic으로 검증한다. server-enforced structured output을 가정하지 않는다. 모델/생성 설정은 plan.json에 고정하고 모델별 자동 fallback 금지.

구독 계정 일치, 추가 유료 크레딧 사용/자동충전 차단을 사람이 확인하고 명시적으로 재개할 때만 아래 실행을 허용한다. 환경변수는 확인 선언일 뿐 실제 결제 차단 장치가 아니다. 프록시 HTTP 200/429만으로 무료임을 보장하지 않는다.

```bash
CAREER_INCLUDED_USAGE_CONFIRMED=yes ../.venv/bin/python benchmark/bench.py --mode live --limit 1 --repeats 1 --output benchmark/runs/live-smoke
```

전체 20명×3회는 각 사용자·반복당 최대 4실제 호출, 세션 최대240호출. 실제 응답에 따라 E검토 생략 가능. 호출당90초, 사용자·반복당600초(단계 경계 검사), 출력9000토큰, 공급자 기본 sampling, SDK retries=0. 시간상한은 진행 중인 요청의 종료를 보장하는 엄격한 deadline이 아니다. 토큰 상한은 전송 UTF-8 byte+최대출력의 보수적 예약량이며 실제 공급자 usage를 따로 기록한다. 프록시 내부 재시도·숨겨진 토큰은 검증 불가. 이러한 제한을 더 강하게 보장하기 전 대량 live 실행은 하지 않는다.

## 결과와 해석

각 runs/<mode>/RESULTS.md, comparison.csv, summary.json, results.jsonl, calls.jsonl.

- 실행 성공률: 성공/(성공+오류), pending 제외. 평가 불가(level=null)는 성공 응답이면 실행 성공이며 별도 LV 분포로 기록.
- 반복 LV 일치: 지정된 모든 반복을 완료한 사용자 중 LV가 모두 같은 사용자 비율. 분모 최대20명. 1회만 실행하면 N/A.
- full_output_consistency는 reason/인용까지 포함한 완전 일치이며 조건별 상태 일치율과 다른 지표다.
- 시간: 결과 행의 wall_seconds와 공유 호출 seconds 합계(logical_seconds)를 분리. mock/replay/캐시 시간이 live 속도를 대표하지 않음.
- 인용 문제: 실제 인용 불일치와 met 근거 누락 등을 issues에 각각 기록. 의미 오류/교정·훼손률 아님.
- LV/조건 정확도, 과대·과소 인정, 근거 의미, 미확인 정확도, 검토 교정/훼손률은 정답 없어 N/A. 재평가도 최초 제출뿐이라 N/A.
- 비용은 가격/과금 확인 전 N/A, mock 사용량도 0원으로 가장하지 않음. 원시 API 호출 건수는 0으로 명시.
- E는 unknown·conflict·상위 met·기여/위험 미확인·인용 문제를 검토한다. 보수적 정책이므로 전체 검토에 가까워질 수 있으며 절감 주장 금지.
- 검토 효과는 C의 before_review와 최종 D/E 비교로 분석할 수 있지만 사람 정답 연결이 선행돼야 한다.
- 현재는 추가 자원 허용 비교. 동일 예산 대조·분류별 품질 집계·사람 정답 import는 후속 작업. 자동 우승 선정하지 않는다.

공식 참고: https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat — 구조화 출력도 의미 오류가 있을 수 있어 형식·근거·최종 규칙을 분리했다.
