# 실험 설계

이 프로그램은 Career 서비스와 독립된 로컬 실험이다. 입력은 manifest로 고정한 코드·Markdown·JSON/JSONL·실행 기록뿐이며 제출 프로젝트를 실행하지 않는다.

- Rule-only: 정규식 하나의 파일 가산점이 아니라 구현, 실행, 기여, 통합, 개선 전후라는 서로 다른 사실을 추출한다. 의미를 확인할 수 없으면 unknown이다.
- LLM-only: 원문과 기준표를 한 번에 주고 기준 상태와 최종 LV를 직접 받는다. 스키마와 인용 위치는 검사하지만 최종 LV를 공통 규칙으로 덮지 않는다.
- 고정 워크플로: prepare → LLM interpret → citation verify → shared adjudication 순서가 코드로 고정돼 있다. 여러 호출 여부와 무관하게 agent라고 부르지 않는다.
- Single-agent: 하나의 모델이 list/read/search/finish를 매 반복마다 선택하며, 실제 읽은 원문에서 낸 상태를 공통 판정기로 계산한다.
- Multi-agent: 분석자와 검토자가 각각 같은 제한 도구로 탐색한다. 검토자는 분석 결과를 참고하되 원문을 직접 확인하고, 동의 여부가 아니라 검토 상태를 공통 판정기에 넣는다.

A/C/D/E는 `criteria.adjudicate`를 공유한다. 모든 방식의 `source_scope`는 manifest 자료 범위이고 `actually_read`는 실제 읽은 범위다. 기준 답안은 manifest 밖 `gold`에 있어 실행기와 도구가 접근하지 못한다.

일반 Python과 LangGraph StateGraph는 같은 네 분석 함수를 사용한다. 둘 다 SQLite 지속 체크포인트를 사용하고, 저장 전 실패는 재호출될 수 있다는 동일 조건으로 복구 실험한다. StateGraph는 LangGraph와 별도 경쟁 기술이 아니라 LangGraph의 실행 구성이다.
