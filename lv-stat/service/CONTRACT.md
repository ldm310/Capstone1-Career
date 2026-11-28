# 스테이징 LV 서비스 약속 (2026-11-27 첫 판, 2026-11-28 보완)

웹(Next.js)과 분석 작업자(Python)가 같은 EC2에서 파일로 주고받는 형식이다. 결정 배경은 [../CLAUDE.md](../CLAUDE.md)의 '스테이징 LV 서비스'.

## 폴더

- 웹의 `CAREER_DATA_DIR`(스테이징 `~/career-data-staging`) 아래 `lv-stat/`를 쓴다. 작업자는 `--data-dir <CAREER_DATA_DIR>/lv-stat`로 받는다.
  - `jobs/<jobId>.json`: 분석 요청 한 건. 웹이 만들고(`queued`), 그 뒤로는 작업자만 고친다.
  - `profiles/<profileKey>.json`: 사람마다 마지막 분석 결과. 작업자만 쓴다.
  - `work/`: 작업자의 임시 폴더(받은 레포). 분석이 끝나면 지운다.
- `profileKey` = `sha256(namespace + ":" + subjectId)`의 16진수 앞 32자.
- 모든 쓰기는 같은 폴더의 임시 파일에 쓴 뒤 `rename`으로 바꾼다(반쯤 쓴 파일을 읽지 않게). 임시 파일 이름은 `.`으로 시작하고 양쪽 모두 읽지 않는다.
- 파일은 소유자만 읽고 쓴다(0600, 폴더 0700). 웹과 작업자는 같은 OS 사용자로 돈다.
- `jobId`는 서버가 만든 uuid v4(소문자)다. 양쪽 모두 이 모양이 아닌 파일 이름은 읽지 않는다.

## jobs/<jobId>.json

웹이 만들 때:

```json
{"id": "<uuid v4>", "namespace": "staging", "subjectId": "<로그인 사용자 id>", "login": "<GitHub 아이디>",
 "input": "<사용자가 넣은 주소>", "status": "queued", "createdAt": "<ISO 8601>"}
```

작업자가 더하는 칸: `status`(`queued` → `running` → `done` | `failed`), `stage`(사람이 읽는 한국어 단계 이름), `progress`(`{"done": n, "total": m}`, 없으면 null), `startedAt`, `finishedAt`, `error`(실패 이유 한 줄, 한국어. 실패일 때만 있고 null로 쓰지 않는다), `profileKey`(done일 때).

- 쓰는 차례: 작업자는 프로필을 먼저 다 쓴 뒤에 요청을 `done`으로 바꾼다. 그래서 웹이 `done`을 본 때에는 그 요청의 프로필(`jobId`가 같음)이 이미 있다.
- 작업자가 다시 시작하면 `running`이던 요청은 `failed`(`작업자가 다시 시작되어 중단됐습니다. 다시 요청해 주세요.`)로 닫는다.

- 단계 이름: `대기` · `레포 찾기` · `레포 받기` · `색인` · `규칙 적용` · `계산` · `끝` · `실패`.
- 작업자는 한 번에 하나만 돌리고, `createdAt`이 이른 것부터 집는다.
- 웹은 사용자마다 `queued`·`running`인 요청을 하나만 두고, 전체 `queued`가 20건이면 더 받지 않는다(「Claude 임시값」).
- 데모 계정(여럿이 함께 쓰는 공개 로그인)은 분석을 요청하지 못하고, 공고 화면도 프로필을 읽지 않는다(「제안」: 결과는 넣은 사람에게만 보인다).

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
- `B`에는 `note`(한 줄 설명, 예: `백엔드 게이트 통과 레포 없음`, `백엔드 게이트를 판정하지 못함(LLM 보충 끔)`)가 더 있을 수 있다. 웹은 모르는 칸을 무시한다.
- `L.best`: 가장 높은 언어. 언어가 하나도 없으면 `null`.
- LLM 보충을 끈 판에서는 LLM 확인을 기다리는 변수를 '모름'으로 센다. 확인된 값이 0이면 평균에서 빼고, 0보다 크면 확인된 만큼으로 단계를 매긴다.
- `languages`: 언어 이름(GitHub Linguist 이름: `Java`, `Kotlin`, `Python`, `JavaScript`, `TypeScript`, `Go`, `C`, `C++`, `C#`, `Swift`, `Dart`, `Ruby`, `PHP`, `Rust`, `Scala` 등) → 그 언어의 LV.
- 팀 카테고리 코드 Q·S·H는 재지 않으므로 칸이 없다.

## 공고 문장 점수 (웹이 읽을 때 계산)

`score(profile, {text, categoryCodes})`:

1. `categoryCodes`에서 L·B·D·E·O·F·A만 남긴다. 그 카테고리의 `lv`가 `null`이면 뺀다.
2. 남은 것이 없으면 점수 없음(모름). 그 문장은 차트에 넣지 않는다.
3. 카테고리마다 값을 정한다. L은 문장에 적힌 언어가 있으면 그 언어들의 `languages` 값 중 가장 높은 것(안 쓴 언어는 0), 없으면 `categories.L.lv`. 나머지는 `categories.<code>.lv`.
4. 점수 = 값들의 평균 × 20을 반올림한 0~100 정수.

비교 값(파란 선)은 넣지 않는다(`reference_score` = null). 웹의 공고 LV 행에는 점수를 실제로 낸 카테고리(`usedCodes`)를 따로 둔다. 레이더 차트는 그 축에만 값을 놓는다(판정 불가 카테고리의 축에 다른 카테고리 값이 들어가지 않게).

## 작업자 실행

```
python3 -I -u lv-stat/service/worker.py --data-dir <dir> [--once] [--max-minutes 20] [--poll 5] [--self-check]
```

- 환경 변수 `LV_GITHUB_TOKEN`(없어도 돈다. 없으면 GitHub API 시간당 60번 제한). 값은 로그에 찍지 않는다.
- Python 3.10 이상, 표준 라이브러리와 `git`만 쓴다. 받은 레포의 코드는 실행하지 않는다.
- 분석 한 건의 시간 상한은 20분이다(「Claude 임시값」). 받기는 (상한 − 마무리 4분)의 50%, 색인은 80%까지 쓰고, 규칙 적용은 상한 4분 전까지, 마무리(s2_final·계산)는 각 2분 안에 끝낸다. 시간이 모자라면 받은 만큼으로 끝내고 `repos.notes`에 '시간 상한' 메모를 남긴다.
- 400MB가 넘는 레포는 `--filter=blob:none`으로 받고, 내 커밋이 바꾼 경로의 판만 한 번에 받는다(「Claude 임시값」 400MB, 사용자 결정 2026-11-26). 받은 뒤에는 부분 clone 설정을 지워 더 받으러 가지 않는다(git 2.45 전 판에서도).
- `--self-check`는 배포 때 지금 데이터 폴더로 돈다. 요청을 닫거나 고치지 않고, 결과(`OK` 또는 `자체 점검 실패: …`)만 stdout에 찍는다. git 판은 찍지 않는다(배포 출력이 공개 CI 로그에 남음).
