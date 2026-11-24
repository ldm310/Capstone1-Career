# lv-stat

사용자 GitHub의 본인 코드 줄을 근거로 역량 레벨·STAT을 계산하는 파트입니다(담당: 동민).

## 지금 상태 (2026-11-24)

- 설계 중입니다. 카테고리별 레벨 계산 방법과 변수 단계는 아직 정하지 않았고, 팀 확인을 받은 뒤 개발을 시작합니다.
- 카테고리는 선영 님이 고정한 `flat-10-infra-review-20261119`(기술 카테고리 10개)를 기준으로 검토합니다.
- 결과를 저장할 자리는 `frontend/docs/user-posting-levels.md`의 `career_lv_*` 표입니다.
- 결정과 미정 사항은 [docs/2026-11-14-역량-stat-변경-방식.md](docs/2026-11-14-역량-stat-변경-방식.md)에 있습니다.

## 들어 있는 것

| 폴더 | 내용 |
|---|---|
| `docs/` | 레벨 방식 변경 메모와 손그림 3장 |
| `pipeline/` | GitHub 레포에서 본인 줄을 뽑아 근거 묶음을 만드는 코드(Python 표준 라이브러리 + git). 설명은 `pipeline/HANDOFF-20261112.md` |
| `schemas/` | 결과 JSON 형식 |
| `examples/shopmall-eun/` | 직접 만든 가짜 레포로 낸 예시 |

- 받은 레포의 코드는 실행하지 않고 git 기록만 읽습니다.
- 공고 글과 측정에 쓴 다른 사람의 레포 목록은 공개 레포라 넣지 않았습니다.
- 공고 매칭 코드(`tag_postings.py`, `match.py`)는 폐지된 초기 LV 기준에 묶여 있어 지금은 쓰지 않습니다.

## 시험

```
python3 lv-stat/pipeline/selftest.py
```

합성 git 레포만 쓰고 네트워크를 쓰지 않습니다. 2026-11-24 기준 97/97 통과입니다.

develop에 합칠 때는 팀 규칙대로 `.github/workflows/ci.yml`에 lv-stat 잡을 더해야 합니다. 잡에서 무엇을 돌릴지는 아직 정하지 않았습니다.
