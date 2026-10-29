# Gemini 직접 연결

사용자가 Free tier 및 Cloud Billing 미연결을 확인한 후에만 실행한다.
키는 `~/.config/career-benchmark/gemini.env`의 GEMINI_API_KEY에서 읽는다.
파일 권한은 600이어야 한다. 쉘 source/eval을 사용하지 않으며 키를 출력하지 않는다.
SDK google-genai 2.26.0, Gemini Developer API만 사용, Vertex AI 비활성화.
SDK 전체 시도 1회, 오류에서 전체 실행 중단, 유료/모델/키 자동 fallback 없음.
확인 환경변수는 사용자 확인 표시이지 공급자 결제 설정을 검사하거나 차단하는 장치가 아니다.

## 모델 선정 기록

2026-10-15 gemini-2.5-flash 생성 요청은 404로 2회 실패했다.
모델 목록에는 존재하지만 서버는 신규 사용자에게 제공되지 않는다고 응답했다.
gemini-3.8-flash를 권장했고 공식 가격표 Standard Free Tier의 입력/출력 무료를 확인해 모델을 변경했다.
실패 결과는 gemini-free-smoke 및 gemini-free-smoke-v2에 보존한다.
무료 서비스 자료 처리 조건을 고려해 이번에는 합성 자료만 전송한다.

https://ai.google.dev/gemini-api/docs/pricing
https://ai.google.dev/gemini-api/docs/structured-output

## 실행

```bash
cd /Users/idongmin/Desktop/experiments/lv-evaluation/career-mock20-v1
../.venv/bin/python -m pytest test_dataset.py benchmark/test_bench.py benchmark/test_gemini.py -q
CAREER_GEMINI_FREE_CONFIRMED=yes ../.venv/bin/python benchmark/bench.py --mode live --provider gemini --limit 1 --repeats 1 --output benchmark/runs/gemini38-free-smoke
```

20명 실행은 --limit 20 및 새 출력 폴더를 사용한다. provider/model은 manifest와 캐시 키에 포함된다.
Gemini와 Codex 결과를 같은 모델 실험으로 합산하지 않는다. 현재 JSON MIME 지정과 Pydantic 검사이며 서버 측 JSON Schema 강제는 사용하지 않는다.
Gemini 입력·출력·thinking·total 토큰을 원장에 별도 기록한다. 정확도와 실제 청구 확인은 여전히 N/A다.

## 이번 실제 실행 결과

- 테스트: 37 passed.
- Gemini 2.5 Flash: 생성 요청 2회, 모두 404(신규 사용자 미지원). 진단용 모델 목록/정보 조회는 성공했다.
- Gemini 3.8 Flash: 생성 요청 1회, 89.39초 후 HTTP 504 `Deadline expired before operation could complete.`
- `gemini38-free-smoke`: A 완료 1, C 시스템 오류 1, B/D/E 미실행. 모델 평가 성공 0.
- 429 한도 초과나 유료 전환 오류로 확인된 것은 아니다. 사용량 응답이 없으므로 사용 토큰/비용을 0으로 추정하지 않는다.
- 자동 재시도 없이 중단했고 20명 실행은 시작하지 않았다. 다음에는 제한 시간을 늘린 별도 실험 또는 입력/출력 크기를 줄인 사전 시험이 필요하다. 변경 전후 시간은 동일 조건 비교로 합치지 않는다.
