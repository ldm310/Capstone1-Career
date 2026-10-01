# 첫 공개 프로젝트 검토 — draft

- 출처: https://github.com/ruizguille/rag-from-scratch
- 고정 커밋: `0f2f4927873fde7d8479c243a21a77ea8a391e9a`
- 라이선스: MIT, 복사본의 LICENSE 보존.
- 자료 범위: README, Python 소스 5개, pyproject.toml. 영화 대본/PDF는 수집하지 않았다.
- `data/public-pilot/`은 개발 목적의 별도 수집 폴더다. 기존 synthetic benchmark 및 최종 평가에는 섞지 않는다.
- 제출 코드와 해당 의존성을 실행/설치하지 않았다.

## 추천 정책 (사람 승인 전 draft)

| LV | 필수 확인 | 예시 |
| --- | --- | --- |
| LV1 기초 사용 | 문서 처리·검색·검색 문맥을 사용한 답변 생성, 해당 경로 실행 기록, 평가 대상자의 기여 | 질문 하나에 대해 검색 문서와 답변이 남은 실행 로그 |
| LV2 프로젝트 적용 | LV1 + 사용자 입력부터 RAG 출력까지 연결된 실제 사용 흐름 | CLI·웹·API 중 어느 형태든 입력→검색→답변 연결 |
| LV3 개선·문제 해결 | LV2 + 문제와 변경 내용 + 동일 평가 조건의 개선 전후 결과 | 동일 질문 집합에서 recall@k/정답률/지연 개선 및 부작용 확인 |

상위 LV는 하위 LV 조건을 포함한다. 실행 방법 설명과 테스트 코드는 실행 결과를 대신하지 않는다. 개인 기여는 단순 저장소 소유자나 패키지 authors 필드로 확정하지 않는다. 자료가 없는 기준은 unknown, 동일 조건의 상반된 자료는 conflict로 기록하고, 확인 가능한 LV가 없으면 null이다.

## 원문 검토 초안 (AI 작성, gold 아님)

- rag.use: 코드상 확인. loader.py는 분할·임베딩·저장, vector_store.py는 유사도 검색, rag.py는 검색 결과를 프롬프트에 넣고 모델 호출.
- rag.project_integration: 코드상 CLI 질문→검색→답변 출력 흐름 확인. CLI도 프로젝트 통합으로 허용한다.
- rag.executed: 선택한 자료에 실제 실행 기록이 없어 unknown.
- rag.contribution: 평가할 지원자가 지정되지 않았고 개인 작업 범위 자료가 없어 unknown.
- rag.improvement: 선택한 자료에 동일 평가 조건의 전후 결과가 없어 unknown.
- 따라서 현재 개인의 confirmed_level은 null. 저장소 개발자의 실제 능력에 대한 판단이 아니다.

## 검토자

초기에는 사용자 1명이 코드 인용과 판정 이유를 검토하며 시작할 수 있다. AI는 답안 초안 작성만 지원한다. 보고용 평가에서는 팀원/교수님 등 RAG 코드를 읽을 수 있는 두 번째 사람이 독립 검토하고 불일치를 조정하는 것을 권장한다. 2명은 실행의 기술적 필수 조건이 아니다.

## API 선택

CLIProxyAPI는 계정/구독/상위 공급자 연결을 API 형태로 중계하는 소프트웨어다. 무료 추론 용량을 자체 제공하는 것은 아니다. 공식 저장소: https://github.com/router-for-me/CLIProxyAPI

사용하려면 실행 중인 프록시 URL, 프록시 인증 설정, 실제 사용 가능한 모델 ID, 연결된 계정과 할당량이 필요하다. 현재 live 어댑터는 Responses structured parsing을 사용하므로 프록시/백엔드가 동일 기능을 처리하는지 실제 호출로 확인해야 한다. 이번에는 설치·로그인·live 호출을 수행하지 않았다.

무료 실험 대안은 Gemini Developer API의 무료 등급 대상 모델이다. 계정/모델별 제공 여부와 제한을 확인해야 하며 현재 어댑터에 Gemini 공식 SDK 연결은 아직 없다. 가격: https://ai.google.dev/gemini-api/docs/pricing , 제한: https://ai.google.dev/gemini-api/docs/rate-limits

## 해석 제한

이 공개 프로젝트 한 개는 자료 수집과 근거 판독의 첫 사례다. 30~50개는 이후 파일럿 목표이며 시작의 선결조건이 아니다. Rule-only의 현재 패턴은 vector_store.query와 CLI 통합을 놓칠 수 있다. mock은 같은 규칙을 사용하므로 이 사례에서도 실제 모델의 이해도를 측정할 수 없다.
