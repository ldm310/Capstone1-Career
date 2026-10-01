# Career LV evaluation benchmark

Career 서비스가 아직 없다는 전제로 만든 독립 Python 실험 프로그램이다. FE, 백엔드, 외부 DB, 배포 환경을 사용하지 않으며 제출 프로젝트 코드도 실행하지 않는다. 현재 지원 기술은 RAG 하나이고 기준표·합성 자료·예상 답안은 모두 **draft**다.

## 1. 환경 구성

테스트한 Python은 3.13.15이며 지원 범위는 3.11~3.13이다. 패키지는 정확한 버전으로 고정되어 있다.

```bash
cd experiments/lv-evaluation
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
pytest
```

버전 선택은 2026-10-01에 공식 문서와 패키지 인덱스를 확인했다. OpenAI 공식 Python SDK의 Responses structured parsing을 live 어댑터에 사용하고, LangGraph의 StateGraph와 SQLite checkpointer를 비교 실행기에 사용한다.

- [OpenAI API quickstart](https://platform.openai.com/docs/quickstart)
- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/)
- [pytest documentation](https://docs.pytest.org/en/stable/)

## 2. 모드

- `mock`: API 없이 전체 연결과 에러 처리를 확인한다. Agent도 list → search → read → finish를 실제 반복한다.
- `live`: `OPENAI_API_KEY`가 있을 때만 공식 SDK로 호출한다. 원문/응답의 외부 전송 정책을 먼저 확인해야 한다.
- `replay`: 저장한 동일 구조화 응답을 재생해 모델 변동을 제거한다. 실행기 비교의 기본 모드다.

모델, 생성 설정, 기준표, 자료 버전과 사례별 호출/도구/토큰/시간 상한은 `config/experiment_plan.json`에서 관리한다. 가격이 없으면 비용은 N/A다.

## 3. 다섯 구성 실행

```bash
# 모든 구성, 모든 합성 개발 사례, 2회 반복
lv-eval run --mode mock --methods all --split development --repeat 2 --output reports/mock-benchmark

# 한 구성만 실행
lv-eval run --mode mock --methods rule_only --split development --output artifacts/runs/rule-only

# 배치가 한 사례의 시스템 오류를 판정 보류와 구분해 기록하는지 확인
lv-eval run --mode mock --methods all --split development --inject-error-case mention_only --output artifacts/runs/mock-error-check

# 명시적인 실제 API 실행(첫 구조 비교에서는 plan의 같은 모델 사용)
export OPENAI_API_KEY='...'
lv-eval run --mode live --methods all --split development --repeat 2 --output artifacts/runs/live-benchmark
```

live 응답에는 민감한 원문이 포함될 수 있으므로 `artifacts/runs/`는 Git에서 제외한다. 키를 파일에 쓰지 않는다. `llm_only`는 모델이 반환한 최종 LV를 보존하며, 나머지 네 방식은 같은 판정기를 사용한다.
공정한 호출 계수를 위해 공식 SDK의 자동 재시도는 끈 상태이며, 현재 `retries=0`으로 기록한다. 재시도 정책을 실험하려면 명시적 계수·비용 누적 로직과 함께 별도 조건으로 추가한다.

## 4. Python vs LangGraph replay 비교

```bash
lv-eval compare-runners \
  --case-id project_lv2 \
  --replay-file data/replay/project_lv2.workflow.jsonl \
  --checkpoint-dir artifacts/checkpoints \
  --output reports/runner-comparison
```

같은 prepare/interpret/verify/decide 함수와 저장 응답을 일반 Python 및 LangGraph StateGraph에 연결한다. 둘 다 로컬 SQLite 체크포인트, 동일한 저장 전 실패 주입, 새 실행기 인스턴스를 통한 재시작 복구를 사용한다. 정상 동일성, 시간, 보존 단계, 복구, 중복 호출, 지원 코드량을 기록한다. 결과는 이 워크플로에만 해당한다.

## 5. 실제 자료 검토와 최종 벤치마크

먼저 [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md)를 따라 기준표와 답안을 사람에게 검토받는다. 실제 자료는 `data/final/projects/`, 답안은 `data/final/gold/expected.jsonl`에 둔다. 두 경로의 내용은 기본적으로 Git에서 제외된다. 답안 파일은 manifest에 넣지 않으므로 프롬프트와 Agent가 접근할 수 없다.

결과를 보기 전에 `config/experiment_plan.json`의 품질·판정 범위·비용·시간 gate를 채운다. gate가 비어 있거나 final 답안이 `human_reviewed`가 아니면 우승 구성을 선언하지 않는다.

```bash
lv-eval run --mode live --methods all --split final --repeat 3 --output artifacts/runs/final-benchmark
```

각 실행은 원본 결과 `.jsonl`, 방식별 집계 `.csv`, 해석 보고서 `.md`를 같은 basename으로 만든다. 지표의 단위와 분모는 [docs/METRICS.md](docs/METRICS.md), 구조와 공정성 조건은 [docs/DESIGN.md](docs/DESIGN.md)에 있다.

## 6. 새 기술 기준표 추가

`config/rag.criteria.json`과 같은 스키마로 기술별 파일을 만들고 criterion extractor/프롬프트 선택을 등록한다. 반드시 기준 ID, LV, 필수 조건, 허용 근거, unknown/conflict 처리, 상위 LV의 포함 관계를 명시한다. 사람 승인 전에는 `status: draft`, `reviewed_by_human: false`를 유지한다.

## 현재 한계

포함된 10개 사례는 요구된 오류 유형을 통과시키기 위한 합성 개발 fixture다. 30~50개 사람 검토 프로젝트 파일럿, 실제 API 실행, 실제 공급자 가격에 따른 비용, 서비스 업로드/파싱/권한/운영 실패 검증은 아직 수행하지 않았다.
