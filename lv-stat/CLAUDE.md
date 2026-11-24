# lv-stat · 역량 LV·STAT (동민 파트)

GitHub에서 본인 코드 줄을 뽑아 역량 근거를 만들고, 카테고리마다 레벨·STAT을 계산하는 파트다. 2026-11-24에 동민의 로컬 작업 폴더(career-stat)에서 필요한 것만 옮겨 왔다.

## 먼저 읽을 것

1. [docs/2026-11-14-역량-stat-변경-방식.md](docs/2026-11-14-역량-stat-변경-방식.md): 지금 결정, 선영 님 카테고리, 팀 LV 자리. 손그림 3장은 같은 이름의 폴더에 있다.
2. [pipeline/HANDOFF-20261112.md](pipeline/HANDOFF-20261112.md): 내 줄 뽑기 코드 설명(11-12판). 공고 매칭 부분은 폐지된 기준이다.

## 지금 결정 (사용자)

- 초기 LV 기준(LLM 4개로 공고 줄마다 정한 요구 LV)은 폐지했다(2026-11-14).
- 선영 님(Seonye32)의 임베딩 카테고리에 맞춰 카테고리마다 STAT·레벨을 만든다. 팀 레포에 고정된 10개(버전 `flat-10-infra-review-20261119`)를 그대로 쓸지는 사용자 확인 전이다.
- 카테고리 레벨은 그 카테고리의 변수(관련 코드 T/F, 커밋 수, 바꾼 줄 수, 기간 등)로 계산한다. 사용자 예시는 (3 + 4 + 3) ÷ 3 ≈ 3.3이고, 계산 방법은 바뀔 수 있다.
- **계산 방법과 카테고리별 변수 단계는 사용자가 정하고, 팀 컨펌을 받은 뒤 개발을 시작한다.** 그 전에 Claude는 숫자나 추천을 먼저 내지 않고, 구현하지 않는다. 물으면 「참고(결정 아님)」로 짧게 답한다.
- 분석 범위: 레포마다 기본 브랜치(main)·develop·dev의 본인 줄만 본다.

## 미정

- 카테고리 10개를 그대로 쓸지
- STAT 계산(변수, 단계 기준, 평균·중앙값), 공고 충족 판정에 쓸지, 화면 표시
- 추출기의 난이도 LV(키별 LV1~5 규칙)를 카테고리 레벨에 쓸지
- 공고 줄이 요구하는 레벨을 무엇으로 정할지(공고 글에는 커밋 수·줄 수가 없다)

## 작업 규칙

- 한국어로 핵심만 답한다. 사용자 생각이 틀리면 분명히 말한다.
- 정책·세부는 혼자 정하지 않고 묻는다. 정하지 않은 것은 「미정」, Claude 의견은 「제안」으로 적는다.
- 증거를 지어내지 않는다. 합성 데이터는 합성이라고 쓰고, 재지 않은 정확도는 N/A로 둔다.
- 받은 레포의 코드는 읽기만 하고 실행하지 않는다(빌드·설치·시험 포함).
- **공개 레포다.** 비밀값(`.env`·토큰·DB 주소·암호), 공고 글(회사·제목·링크·요건 문장), 지인 계정·레포 이름을 파일이나 commit에 넣지 않는다.
- 팀 DB는 읽기 전용으로만 접속한다.
- 유료 API(Claude 등)는 부르기 전에 비용을 알린다. 결제나 한도가 모호하면 멈춘다.
- `feature/lv-stat`에서 작업하고 PR로 develop에 합친다. 합칠 때 `.github/workflows/ci.yml`에 lv-stat 잡을 더한다(팀 규칙). commit·push는 사용자가 말할 때만 한다.
- 다른 파트 폴더(`backend/`·`frontend/`·`job-skill/` 등)는 읽기만 한다.

## 팀 쪽 자료 (develop 기준)

- 카테고리: [backend/docs/skill-category-api.md](../backend/docs/skill-category-api.md), `backend/src/main/resources/skill-categories/reviewed-20261119.json`(문장 SHA-256 → 카테고리 코드, 원문 없음)
- LV 저장 자리: [frontend/docs/user-posting-levels.md](../frontend/docs/user-posting-levels.md), `db/migrations/06-user-posting-levels.sql`(`career_lv_*` 표, 0~100 점수). 지금 점수는 화면 확인용 더미다.

## 폴더

- `docs/`: 결정 메모와 손그림
- `pipeline/`: GitHub에서 내 줄을 뽑는 코드(Python 표준 라이브러리 + git)
  - 내 줄 뽑기: `clone.sh`(받기) → `identity.py`(레포마다 내 git 이름 찾기) → `bundle.py`·`extract.py`(내 줄 → 근거 묶음, 규칙은 `lv1_rules.py`·`lv_dict.py`)
  - 점검·stat: `make_packets.py` → `verify_agent.py`(Claude Haiku 점검, 유료) → `apply_verdicts.py` → `to_stat.py`(`keys.py`의 키 이름)
  - 한 번에 돌리기: `run_profile.py`(계정 URL)는 공고 파일(`data/postings.json`)이 없으면 레포를 돌기 전에 멈춘다. `run_pipeline.py`(레포 하나)는 1단계(근거 묶음·packet)까지는 공고 파일 없이 돈다. `data/`는 가져오지 않았다.
  - 폐지된 기준에 묶인 것: `tag_postings.py`·`match.py`(줄별 요구 LV), `make_report.py`의 공고 부분
  - 측정용: `run_eval.py`·`audit45.py`·`recall45.py`·`score_verifier.py`(측정 자료 `eval/`는 가져오지 않았다)
  - 시험: `python3 pipeline/selftest.py`(합성 레포만, 네트워크 없음). 2026-11-24에 이 폴더에서 97/97 통과했다.
- `schemas/`: 결과 JSON 형식. `examples/shopmall-eun/`: 합성 레포로 낸 예시
- `repos/`(받은 레포), `out/`(결과), `.env`는 git에 넣지 않는다.
