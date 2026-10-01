# LV evaluation benchmark report

> **synthetic / draft** — 사람이 의미와 예상 답안을 검토한 최종 평가가 아닙니다.

실행 모드: `mock`. 이 수치는 이 저장소의 RAG 합성 개발 사례와 현재 워크플로에만 적용됩니다.

| method | final_lv_accuracy | criterion_accuracy | coverage | over_recognition | under_recognition | deferrals | failure_rate | avg_seconds | total_model_calls | total_tool_calls | total_tokens | total_cost_krw |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_workflow | 1.0000 | 1.0000 | 0.3333 | 0 | 0 | 6 | 0.1000 | 0.0004 | 9 | 0 | 8646 | N/A |
| llm_only | 1.0000 | 1.0000 | 0.3333 | 0 | 0 | 6 | 0.1000 | 0.0005 | 9 | 0 | 8843 | N/A |
| multi_agent | 1.0000 | 1.0000 | 0.3333 | 0 | 0 | 6 | 0.1000 | 0.0025 | 114 | 78 | 58542 | N/A |
| rule_only | 1.0000 | 1.0000 | 0.3333 | 0 | 0 | 6 | 0.1000 | 0.0005 | 0 | 0 | 0 | N/A |
| single_agent | 1.0000 | 1.0000 | 0.3333 | 0 | 0 | 6 | 0.1000 | 0.0012 | 57 | 39 | 19713 | N/A |

## 해석 범위

- 현재 자료는 연결·오류 경로 확인용 합성 개발 자료다. 사람 검토 정답이 없으므로 근거 오류는 N/A이며 우승 구성을 선언할 수 없다.
- 호출·토큰·시간은 실제 사용량이다. mock/replay 토큰은 어댑터가 기록한 결정론적 추정치이며 실제 과금 토큰이 아니다. 가격표가 없으므로 비용은 N/A다.
- Single/Multi-agent는 추가 모델 호출과 도구 호출을 사용한다. 차이는 구조 자체뿐 아니라 추가 자원 효과일 수 있다.
- Rule-only는 명시 패턴에 강하지만 표현 변형과 의미 해석에 약하다. LLM-only는 직접 판정을 보존하므로 일관성·과대 인정 위험을 별도로 관찰해야 한다.
- 고정 워크플로는 단계가 재현 가능하고, 에이전트는 필요한 자료를 선택할 수 있지만 탐색 예산과 누락 위험이 있다.

## 사례 관찰

- `fixed_workflow`: 인정 사례 `basic_lv1`, 보류 사례 `dependency_only`, 시스템/예산 실패 사례 `mention_only`.
- `llm_only`: 인정 사례 `basic_lv1`, 보류 사례 `dependency_only`, 시스템/예산 실패 사례 `mention_only`.
- `multi_agent`: 인정 사례 `basic_lv1`, 보류 사례 `dependency_only`, 시스템/예산 실패 사례 `mention_only`.
- `rule_only`: 인정 사례 `basic_lv1`, 보류 사례 `dependency_only`, 시스템/예산 실패 사례 `mention_only`.
- `single_agent`: 인정 사례 `basic_lv1`, 보류 사례 `dependency_only`, 시스템/예산 실패 사례 `mention_only`.

## 다음 단계

사람이 기준표와 실제 프로젝트 자료/기준 답안을 검토하고, 사전에 품질·범위·비용·시간 gate를 채운 뒤 30~50개 프로젝트 파일럿을 실행해야 한다. 서비스 연결 후에는 실제 업로드 파싱, 권한, 지연, 모델 변경, 프롬프트 인젝션, 관측/재시도 동작을 추가 검증한다.
