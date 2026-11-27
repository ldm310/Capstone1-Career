# 스테이징 LV 서비스 약속 (2026-11-27, 첫 판)

웹(Next.js)과 분석 작업자(Python)가 같은 EC2에서 파일로 주고받는 형식이다. 결정 배경은 [../CLAUDE.md](../CLAUDE.md)의 '스테이징 LV 서비스'.

## 폴더

- 웹의 `CAREER_DATA_DIR`(스테이징 `~/career-data-staging`) 아래 `lv-stat/`를 쓴다. 작업자는 `--data-dir <CAREER_DATA_DIR>/lv-stat`로 받는다.
  - `jobs/<jobId>.json`: 분석 요청 한 건. 웹이 만들고(`queued`), 그 뒤로는 작업자만 고친다.
  - `profiles/<profileKey>.json`: 사람마다 마지막 분석 결과. 작업자만 쓴다.
  - `work/`: 작업자의 임시 폴더(받은 레포). 분석이 끝나면 지운다.
- `profileKey` = `sha256(namespace + ":" + subjectId)`의 16진수 앞 32자.
- 모든 쓰기는 같은 폴더의 임시 파일에 쓴 뒤 `rename`으로 바꾼다(반쯤 쓴 파일을 읽지 않게).

## jobs/<jobId>.json

웹이 만들 때:

```json
{"id": "<uuid v4>", "namespace": "staging", "subjectId": "<로그인 사용자 id>", "login": "<GitHub 아이디>",
 "input": "<사용자가 넣은 주소>", "status": "queued", "createdAt": "<ISO 8601>"}
```

작업자가 더하는 칸: `status`(`queued` → `running` → `done` | `failed`), `stage`(사람이 읽는 한국어 단계 이름), `progress`(`{"done": n, "total": m}`, 없으면 null), `startedAt`, `finishedAt`, `error`(실패 이유 한 줄, 한국어) , `profileKey`.

- 단계 이름: `대기` · `레포 찾기` · `레포 받기` · `색인` · `규칙 적용` · `계산` · `끝` · `실패`.
- 작업자는 한 번에 하나만 돌리고, `createdAt`이 이른 것부터 집는다.
- 웹은 사용자마다 `queued`·`running`인 요청을 하나만 둔다.

## profiles/<profileKey>.json

```json
{
  "schema": "lv-stat-profile/1",
  "method": "lv-stat-s2-20261127",
  "labels": ["2단계 규칙", "LLM 보충 끔", "제안 기준", "본인 확인 안 됨"],
  "namespace": "staging", "subjectId": "...", "login": "...", "jobId": "...", "analyzedAt": "<ISO 8601>",
  "repos": {"found": 12, "analyzed": 11, "failed": 1, "notes": ["..."]},
  "categories": {
    "L": {"name": "프로그래밍 활용", "lv": 3.3, "unknown": 0, "languages": {"Java": 3.3, "Python": 2.0}, "best": "Java"},
    "O": {"name": "운영 배포", "lv": 1.5, "unknown": 0},
    "B": {"name": "백엔드 개발", "lv": 2.0, "unknown": 2},
    "E": {"name": "데이터 엔지니어", "lv": 0.0, "unknown": 0},
    "D": {"name": "데이터베이스", "lv": 2.7, "unknown": 0},
    "F": {"name": "프론트엔드 앱", "lv": 0.0, "unknown": 1},
    "A": {"name": "AI 기술", "lv": 0.0, "unknown": 0}
  }
}
```

- `lv`: 0.0~5.0(소수 첫째 자리). 그 카테고리의 변수가 모두 모름이면 `null`(판정 불가).
- `unknown`: 그 카테고리에서 확인하지 못한 변수·항목 수('모름 n개').
- `languages`: 언어 이름(GitHub Linguist 이름: `Java`, `Kotlin`, `Python`, `JavaScript`, `TypeScript`, `Go`, `C`, `C++`, `C#`, `Swift`, `Dart`, `Ruby`, `PHP`, `Rust`, `Scala` 등) → 그 언어의 LV.
- 팀 카테고리 코드 Q·S·H는 재지 않으므로 칸이 없다.

## 공고 문장 점수 (웹이 읽을 때 계산)

`score(profile, {text, categoryCodes})`:

1. `categoryCodes`에서 L·B·D·E·O·F·A만 남긴다. 그 카테고리의 `lv`가 `null`이면 뺀다.
2. 남은 것이 없으면 점수 없음(모름). 그 문장은 차트에 넣지 않는다.
3. 카테고리마다 값을 정한다. L은 문장에 적힌 언어가 있으면 그 언어들의 `languages` 값 중 가장 높은 것(안 쓴 언어는 0), 없으면 `categories.L.lv`. 나머지는 `categories.<code>.lv`.
4. 점수 = 값들의 평균 × 20을 반올림한 0~100 정수.

비교 값(파란 선)은 넣지 않는다(`reference_score` = null).

## 작업자 실행

```
python3 -I lv-stat/service/worker.py --data-dir <dir> [--once] [--max-minutes 20]
```

- 환경 변수 `LV_GITHUB_TOKEN`(없어도 돈다. 없으면 GitHub API 시간당 60번 제한). 값은 로그에 찍지 않는다.
- Python 3.10 이상, 표준 라이브러리와 `git`만 쓴다. 받은 레포의 코드는 실행하지 않는다.
