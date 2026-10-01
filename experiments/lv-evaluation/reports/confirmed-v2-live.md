# 확정 LV 기준 — 첫 로컬 벤치마크

Multi-agent는 HTTP 429 (ClientError)로 중단됐다. 앞선 구성들의 사용량이 뒤 구성의 한도에 영향을 줄 수 있으므로 구조 자체의 실패율로 일반화하지 않는다. 할당량 회복 후 실행 순서 교대·반복이 필요하다.

초기 gemini-2.5-flash-lite는 신규 사용자 사용 불가(404)로 B~E 요청 각 1회와 진단 요청 1회가 실패했다. 아래 표는 모든 구성을 gemini-3.5-flash-lite로 다시 실행한 별도 실행이다. 초기 실패 요청의 토큰/비용은 미확인이다.

| 단계 | 사용자가 확정한 핵심 기준 | 필요한 증거 |
|---|---|---|
| LV1 | 기본 기능을 구현하고 실행할 수 있음 | 구현 코드, 재현 가능한 실행 방법·결과 |
| LV2 | 요구사항에 맞춰 다른 기능과 연결하고 동작 검증 | 연동 코드, 요구사항 대응 테스트, 적용 이유 |
| LV3 | 문제 측정·분석 후 수정 효과와 한계 설명 | 문제 분석, 변경 코드, 동일 조건 전후 평가, 결과 해석 |

사용자 확정 LV1~3을 v2 기준표로 반영. 세부 근거 해석은 검토 전이며, 상위 LV는 하위 LV 포함.
공개 RAG 프로젝트 1개, 구성별 1회. gemini-3.5-flash-lite, temperature=0. 제출 코드는 실행하지 않음.
기존 합성 예상 답안은 사용하지 않음. 정확도·과대/과소 인정·근거 오류·비용·반복 일관성은 N/A.

| 구성 | 실행 상태 | 확인 LV | 시간(s) | 모델 요청(실패 포함) | 도구 호출 | 입력 토큰 | 출력+추론 토큰 |
|---|---|---|---:|---:|---:|---:|---:|
| rule_only | completed | null | 0.005 | 0 | 8 | 0 | 0 |
| llm_only | completed | null | 4.316 | 1 | 8 | 3992 | 1150 |
| fixed_workflow | completed | null | 3.961 | 1 | 8 | 3985 | 1174 |
| single_agent | completed | null | 14.744 | 8 | 6 | 11684 | 2538 |
| multi_agent | failed | null | 11.353 | 7 | 4 | 10648 | 2313 |

실패 결과의 null은 판정 보류가 아니라 결과 미생성이다. 토큰은 성공 응답에서 확인한 값만 합산하며, 실패 요청의 사용량은 미확인이다.
A의 도구 호출에는 일괄 파일 로딩도 포함된다. 모형 호출이 없는 A의 시간과 실제 네트워크 호출을 포함한 B~E 시간을 구분해 해석한다.

## 기준별 출력

| 구성 | rag.use | rag.executed | rag.reproduction | rag.project_integration | rag.requirements_tests | rag.reason | rag.improvement |
|---|---|---|---|---|---|---|---|
| rule_only | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| llm_only | unknown | unknown | met | not_met | not_met | not_met | not_met |
| fixed_workflow | met | unknown | unknown | met | not_met | unknown | not_met |
| single_agent | unknown | unknown | met | met | unknown | unknown | unknown |
| multi_agent | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

현재 규칙 추출기는 신규 재현 방법·요구사항 테스트·적용 이유·엄격한 개선 기준을 충분히 해석하지 못해 unknown으로 처리한다. A는 확장 전 기준선이며 Rule-based 전체의 성능을 대표하지 않는다.
공개 프로젝트에 실행 결과와 전후 평가가 부족하다. 개인 기여 확인과 사람 검토 정답은 별도 필요하다. 단일 사례·단일 실행으로 우승 기술을 정하지 않는다.

실행: `.venv/bin/python -m lv_eval.pilot`
원시 결과: `artifacts/runs/confirmed-v2-live/summary.json` (Git 제외)
