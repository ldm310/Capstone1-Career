# Final evaluation data (human supplied)

이 디렉터리는 사람 검토를 거친 실제 프로젝트 평가용이다. `projects/<project_id>/cases/<case_id>/` 단위로 자료와 `manifest.json`을 추가한다. 같은 `project_id`의 원본/변형은 반드시 같은 split에 둔다.

기준 답안은 `gold/expected.jsonl`에만 두며 프로젝트의 `manifest.json.files`에는 절대 포함하지 않는다. 이 때문에 프롬프트와 Agent 도구는 기준 답안을 열 수 없다. 실제 자료와 모델 응답, API 키는 기본적으로 Git에 포함되지 않는다.
