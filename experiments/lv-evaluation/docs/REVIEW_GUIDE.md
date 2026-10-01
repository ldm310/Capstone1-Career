# 사람 검토 절차

1. `config/rag.criteria.json`의 각 기준, 포함 관계, 미확인/충돌 정책을 도메인 검토자가 승인하거나 수정한다.
2. 프로젝트별 원본을 `data/final/projects/<project_id>/cases/<case_id>/`에 복사하고 고정 버전/출처/수집일을 별도 기록한다. 실행 로그는 제출된 기록만 사용하며 사용자 코드를 실행하지 않는다.
3. `manifest.json`에는 모델이 볼 수 있는 상대 경로만 넣는다. 비밀, 개인정보, 기준 답안은 넣지 않는다.
4. 두 명의 검토자가 아래 JSONL 양식으로 독립 판정하고 불일치를 합의한다. 합의 전 `review_status`는 `draft`, 완료 후에만 `human_reviewed`다.
5. `project_id`로 그룹 분할한다. 같은 프로젝트의 축약·오염·변형 사례는 개발/최종 평가에 흩어 놓지 않는다.
6. 결과를 보기 전에 `config/experiment_plan.json`의 네 decision gate를 채우고 Git에 기록한다.
7. 최종 자료는 Git에서 기본 제외되므로 승인된 보안 저장 위치에서 실행한다.

기준 답안 한 줄 양식:

```json
{"case_id":"case-001","project_id":"project-001","review_status":"draft","confirmed_level":null,"criteria":{"rag.use":"unknown","rag.executed":"unknown","rag.contribution":"unknown","rag.project_integration":"unknown","rag.improvement":"unknown"},"notes":"reviewer notes"}
```

30~50개 초기 파일럿은 **프로젝트 수** 기준으로 계획한다. 자동 생성 사례로 숫자를 채워 검증 자료라고 부르지 않는다.
