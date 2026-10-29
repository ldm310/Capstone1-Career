# 연결 검증 결과 - 2026-10-15

실행 위치: `/Users/idongmin/Desktop/experiments/lv-evaluation/career-mock20-v1`

실제로 실행한 명령:

```bash
../.venv/bin/python -m pytest test_dataset.py benchmark/test_bench.py -q
../.venv/bin/python benchmark/bench.py --mode mock --output benchmark/runs/mock
../.venv/bin/python benchmark/bench.py --mode replay --replay-source benchmark/runs/mock --output benchmark/runs/replay
../.venv/bin/python benchmark/bench.py --mode mock --output benchmark/runs/mock
```

- pytest: 35 passed.
- mock: 사용자20명 × 반복3 × A~E = 300개 결과 완료. 물리 mock 응답 생성240개, 실제 API0회.
- replay: 300개 결과 완료, 원본 mock과 id/result/issues/review_targets 모두 동일.
- 동일 mock 재실행: 새 응답0개, 결과 행 추가0개. 300행/240응답 유지.
- 각 방식60/60 완료. 이 값은 실행 연결 완료율이며 LV 판정 정확도가 아니다.
- E 모든 사례에서 검토 발생. 현재 mock/선별 정책에서는 D 대비 호출 절감 없음.
- 테스트: 31조건 스키마, 누적 선행조건, 개인기여 gate, PDF 입력, 원문 해시, Git 버전 불일치, 경로 차단, 인용 오류, B 원래LV보존, C/D/E 추출 공유, E선택범위병합, replay 누락, 호출 예산, live 사전확인 차단, 공급자 오류의 비밀정보 비기록, 잘못된 JSON의 시스템 오류 구분.
- 현재 테스트에서 live 실패 경로는 가짜 클라이언트로만 실행. 실제 공급자 호출은 없다.
- 기존 데이터/서비스/보관자료 변경 없음. 새 코드에는 이전 pilot50/pilot100/executable-study import 없음.

부족한 것: 프록시 계정 과금 차단 확인, 실제 live 실행, 사람 검토 정답 import·정확도 및 검토 교정/훼손 집계, 직무별 조건부 적용 정책 확정, 상위LV 실제 활용 긍정 사례, 동일 예산 대조실험. 현재 우승 구성은 결정하지 않는다.
