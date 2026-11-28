# lv-stat

사용자 GitHub의 본인 코드 줄을 근거로 역량 레벨·STAT을 계산하는 파트입니다(담당: 동민).

## 지금 상태 (2026-11-24)

- 개발 중입니다. 카테고리 7개의 LV 계산 규칙은 [docs/lv-calc-7categories-2026-11-24.md](docs/lv-calc-7categories-2026-11-24.md), 백엔드 기준은 [docs/backend-lv-v5-6vars-final-2026-11-24.md](docs/backend-lv-v5-6vars-final-2026-11-24.md)에 있습니다. 단계 시작값 같은 숫자는 임시값이고 8명 테스트로 맞춥니다.
- 7개 카테고리를 선영 님이 고정한 기술 카테고리 10개(`flat-10-infra-review-20261119`)와 어떻게 잇는지는 아직 정하지 않았습니다.
- 결과를 저장할 자리는 `frontend/docs/user-posting-levels.md`의 `career_lv_*` 표입니다.
- 결정과 미정 사항은 [docs/2026-11-14-역량-stat-변경-방식.md](docs/2026-11-14-역량-stat-변경-방식.md)에 있습니다.
- 2026-11-27부터 스테이징 LV 서비스 첫 판(`service/`)이 있습니다. 스테이징 웹에서 GitHub 계정 주소를 넣으면 작업자가 분석하고, 공고 상세의 레이더 차트에 공고별 LV가 나옵니다(2단계 규칙, LLM 보충 끔).

## 들어 있는 것

| 폴더 | 내용 |
|---|---|
| `docs/` | 레벨 방식 변경 메모와 손그림 3장 |
| `pipeline/` | GitHub 레포에서 본인 줄을 뽑아 근거 묶음을 만드는 코드(Python 표준 라이브러리 + git). 설명은 `pipeline/HANDOFF-20261112.md` |
| `schemas/` | 결과 JSON 형식 |
| `examples/shopmall-eun/` | 직접 만든 가짜 레포로 낸 예시 |
| `service/` | 스테이징 LV 서비스 작업자(Python 3.10 이상, 표준 라이브러리 + git). 웹이 만든 분석 요청을 하나씩 집어 계정의 공개 레포를 받고 카테고리 LV를 계산합니다. 웹과 주고받는 형식은 `service/CONTRACT.md`, 배포는 `deploy/lv-stat/README.md` |

- 받은 레포의 코드는 실행하지 않고 git 기록만 읽습니다.
- 공고 글과 측정에 쓴 다른 사람의 레포 목록은 공개 레포라 넣지 않았습니다.
- 공고 매칭 코드(`tag_postings.py`, `match.py`)는 폐지된 초기 LV 기준에 묶여 있어 지금은 쓰지 않습니다.

## 시험

```
python3 lv-stat/pipeline/selftest.py
```

합성 git 레포만 쓰고 네트워크를 쓰지 않습니다. 2026-11-24 기준 97/97 통과입니다.

```
python3 -m unittest discover -s lv-stat/service/tests
python3 -m unittest discover -s deploy/lv-stat/tests
```

작업자 시험은 합성 레포와 127.0.0.1의 가짜 GitHub API만 씁니다. 배포 시험은 가짜 HOME·sudo·systemctl로 작업자 배포 스크립트와 웹 배포의 LV 스위치(`CAREER_LV_STAT`)를 봅니다.

CI의 `lv-stat` 잡(`.github/workflows/ci.yml`)은 `lv-stat/`·`deploy/lv-stat/`·`deploy/web/deploy.sh`가 바뀌면 Python 3.10으로 위 세 시험을 돌립니다.
