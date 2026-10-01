# Python vs LangGraph executor comparison

> **replay / synthetic / draft** — 같은 저장 응답과 같은 분석 함수를 이 워크플로에서 비교한 결과입니다.

| 항목 | 일반 Python | LangGraph StateGraph |
| --- | --- | --- |
| normal_result | {"confirmed_level": "LV2", "review_required": true, "criteria": [["rag.contribution", "met"], ["rag.executed", "met"], ["rag.improvement", "unknown"], ["rag.project_integration", "met"], ["rag.use", "met"]]} | {"confirmed_level": "LV2", "review_required": true, "criteria": [["rag.contribution", "met"], ["rag.executed", "met"], ["rag.improvement", "unknown"], ["rag.project_integration", "met"], ["rag.use", "met"]]} |
| elapsed_seconds | 0.0039 | 0.0082 |
| failure_preserved_stages | prepare | prepare |
| restart_recovered | True | True |
| restart_process_count | 2 | 2 |
| model_calls_with_restart | 2 | 2 |
| duplicate_model_calls | 1 | 1 |
| duplicate_stage_results | 0 | 0 |
| support_code_lines | 33 | 58 |

정상 결과 동일성은 최종 LV와 기준별 상태를 비교한다. 실패는 `interpret` 계산 뒤 체크포인트 저장 전 주입한다. 두 실행기 모두 로컬 SQLite를 사용하며 실패 프로세스 종료 후 별도 Python 프로세스에서 복구한다.

체크포인트 전에 실패한 호출은 어느 실행기에서도 완료 상태로 저장할 수 없어 재호출된다. 시간은 단일 로컬 replay 관측치라 성능 우열의 근거가 아니다. 기능을 구현하지 않은 항목은 N/A로 표시해야 하며, 이 결과를 다른 그래프나 운영 구조로 일반화할 수 없다.
