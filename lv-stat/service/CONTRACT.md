# 스테이징 LV 서비스 약속 (2026-11-27 첫 판, 2026-11-28 보완)

웹(Next.js)과 분석 작업자(Python)가 같은 EC2에서 파일로 주고받는 형식이다. 결정 배경은 [../CLAUDE.md](../CLAUDE.md)의 '스테이징 LV 서비스'.

## 폴더

- 웹의 `CAREER_DATA_DIR`(스테이징 `~/career-data-staging`) 아래 `lv-stat/`를 쓴다. 작업자는 `--data-dir <CAREER_DATA_DIR>/lv-stat`로 받는다.
  - `jobs/<jobId>.json`: 분석 요청 한 건. 웹이 만들고(`queued`), 그 뒤로는 작업자만 고친다.
  - `profiles/<profileKey>.json`: 사람마다 마지막 분석 결과. 작업자만 쓴다.
  - `work/`: 작업자의 임시 폴더(받은 레포). 분석이 끝나면 지운다.
- `profileKey` = `sha256(namespace + ":" + subjectId)`의 16진수 앞 32자.
- 모든 쓰기는 같은 폴더의 임시 파일에 쓴 뒤 `rename`으로 바꾼다(반쯤 쓴 파일을 읽지 않게). 임시 파일 이름은 `.`으로 시작하고 양쪽 모두 읽지 않는다.
- 요청·결과 파일은 소유자만 읽고 쓴다(0600). `jobs/`·`profiles/`·`work/`는 0700이다(웹은 mode 0700으로, 작업자는 systemd `UMask=0077`로 만든다). 그 위의 `lv-stat/` 폴더는 작업자 배포 스크립트가 러너의 umask로 만들어 0755일 수 있다(안은 모두 소유자만). 웹과 작업자는 같은 OS 사용자로 돈다.
- `jobId`는 서버가 만든 uuid v4(소문자)다. 양쪽 모두 이 모양이 아닌 파일 이름은 읽지 않는다.

## jobs/<jobId>.json

웹이 만들 때:

```json
{"id": "<uuid v4>", "namespace": "staging", "subjectId": "<로그인 사용자 id>", "login": "<GitHub 아이디>",
 "input": "<사용자가 넣은 주소>", "status": "queued", "createdAt": "<ISO 8601>"}
```

작업자가 더하는 칸: `status`(`queued` → `running` → `done` | `failed`), `stage`(사람이 읽는 한국어 단계 이름), `progress`(`{"done": n, "total": m}`, 없으면 null), `startedAt`, `finishedAt`, `error`(실패 이유 한 줄, 한국어. 실패일 때만 있고 null로 쓰지 않는다), `profileKey`(done일 때).

- 쓰는 차례: 작업자는 프로필을 먼저 다 쓴 뒤에 요청을 `done`으로 바꾼다. 그래서 웹이 `done`을 본 때에는 그 요청의 프로필(`jobId`가 같음)이 이미 있다.
- 읽는 차례: 웹(`GET /api/lv-stat/analysis`)은 요청을 먼저, 프로필을 나중에 읽는다(함께 읽으면 `done`인 요청과 옛 프로필이 올 수 있다). 분석 칸은 요청이 `done`인데 프로필의 `jobId`가 그 요청이 아니면(없거나 다른 분석의 것) 끝나지 않은 것으로 보고 같은 간격(5초)으로 3번 더 읽는다(「Claude 임시값」). 그래도 다르면 읽기를 멈추고 `분석 결과를 불러오지 못했어요.`를 보인다. 그사이 GET이 200이 아닌 답을 주거나 연결이 끊기면 기다림을 바로 끝낸다: 요청과 결과를 비우고 더 읽지 않는다(401은 로그인 안내, 404는 칸을 그리지 않음, 그 밖의 답은 그 오류 글, 연결 끊김은 `연결을 확인해 주세요.`).
- 웹은 있는 프로필 파일을 모양(아래 형식, 그 사람의 것인지 포함) 때문에 버리면 서버 기록에 `LV profile ignored` 한 줄을 남긴다(경로·내용은 남기지 않음). 첫 배포에서 두 쪽 약속이 어긋나면 보이게 하려는 것이다.
- 작업자가 다시 시작하면 `running`이던 요청은 `failed`(`작업자가 다시 시작되어 중단됐습니다. 다시 요청해 주세요.`)로 닫는다.

- 단계 이름: `레포 찾기` · `레포 받기` · `색인` · `규칙 적용` · `계산` · `끝` · `실패`. `대기`는 파일에 쓰이지 않는다(웹이 만든 요청에는 `stage`가 없고, 화면은 그때 `대기`로 보인다).
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

비교 값(파란 선)은 넣지 않는다(`referenceScore` = null). 웹의 공고 LV 행에는 점수를 실제로 낸 카테고리(`usedCodes`)를 따로 둔다. 레이더 차트는 그 축에만 값을 놓는다(판정 불가 카테고리의 축에 다른 카테고리 값이 들어가지 않게).

## 스테이징 스위치 (웹)

작업자는 스테이징에만 있다. 웹의 분석 기능은 서버 설정 `CAREER_LV_STAT`가 정확히 `on`일 때만 켜진다(없거나 다른 값이면 꺼짐). 요청 때마다 읽는다.

- 켜는 곳: `deploy/web/deploy.sh`가 웹 서비스 파일에 `Environment=CAREER_LV_STAT=<값>`을 쓴다. 스테이징(3001번) `on`, 운영(main·3000번) `off`. 같은 이름이 그 환경의 `.env`(EnvironmentFile)에 있으면 그 값이 이긴다(systemd 규칙). 로컬 e2e(`frontend/playwright.config.ts`)와 계약 시험은 켜고 돈다.
- 꺼져 있으면: `GET`·`POST /api/lv-stat/analysis`는 세션·요청·결과 파일을 읽기 전에 404이고 데이터 폴더에 아무것도 만들지 않는다. `GET /api/jobs/my-levels`는 프로필을 읽지 않고 저장된 LV(RDS)만 읽는다. `/analysis`의 분석 칸은 GET이 404라 그리지 않는다(첫 GET이 답하기 전에도 그리지 않음). 분류 버전이 없는 공고에서 프로필을 자료로 세지 않는다.
- 막는 것: develop→main 병합 때 작업자가 없는 운영에 분석 기능이 나가 요청이 `queued`로 영영 남는 것.

## 작업자 실행

```
python3 -I -u lv-stat/service/worker.py --data-dir <dir> [--once] [--max-minutes 20] [--poll 5] [--self-check]
```

- 환경 변수 `LV_GITHUB_TOKEN`(없어도 돈다. 없으면 GitHub API 시간당 60번 제한). 값은 로그에 찍지 않는다.
- Python 3.10 이상, 표준 라이브러리와 `git`만 쓴다. 받은 레포의 코드는 실행하지 않는다.
- 분석 한 건의 시간 상한은 20분이다(「Claude 임시값」). 받기는 (상한 − 마무리 4분)의 50%, 색인은 80%까지 쓰고, 규칙 적용은 상한 4분 전까지, 마무리(s2_final·계산)는 각 2분 안에 끝낸다. 시간이 모자라면 받은 만큼으로 끝내고 `repos.notes`에 '시간 상한' 메모를 남긴다.
- 400MB가 넘는 레포는 `--filter=blob:none`으로 받고, 내 커밋이 바꾼 경로의 판만 한 번에 받는다(「Claude 임시값」 400MB, 사용자 결정 2026-11-26). 「제안」(확인 전) 내 경로가 생긴 커밋에서 지워진 남의 파일의 판도 하나씩 받는다(blame이 이름 바꿈을 따라가게. 2026-11-26 결정보다 넓다). 받은 뒤에는 부분 clone 설정을 지워 더 받으러 가지 않는다(git 2.45 전 판에서도).
- 디스크 여유(「Claude 임시값」 2GiB): 작업 폴더는 운영 웹과 같은 디스크다. 받기 전마다 남은 공간에서 그 레포의 예상 크기(400MB 이하는 GitHub size, 큰 레포는 500MB(「Claude 임시값」, 2단계 실측 최대 309MB))를 뺀 값이 2GiB보다 작으면 그 레포부터는 받지 않고 `repos.notes`에 `디스크 여유가 모자라 레포 n개는 받지 못함`을 남긴다(하나도 못 받았으면 실패). 받기·색인 중에 남은 공간이 2GiB 밑으로 내려가도 그 단계를 멈춘다: 받기는 같은 메모(멈춘 레포와 뒤의 레포 수), 색인은 색인한 레포로 계속하며 `디스크 여유가 모자라 레포 n개는 색인하지 못함`. 받기 전 점검이 받기를 멈추면 작업자 로그에 경고 한 줄을 남긴다(레포 수(전체·받음·받지 않음), 남은 공간·그 레포를 받으면 남을 공간·남길 공간(MiB). 경로·레포 이름은 남기지 않는다).
- 메모리(「Claude 임시값」): systemd 유닛이 `MemoryHigh=400M`·`MemoryMax=512M`로 묶는다(`deploy/lv-stat/deploy_worker.sh`). 첫 배포 로그에서 서버 메모리 1905MB 중 사용 가능 751MB였고, 운영 웹·스테이징 웹·백엔드와 같은 서버이기 때문이다. 한도를 넘어 자식 프로세스(git·색인·규칙) 하나가 죽어도 작업자는 계속 돈다(`OOMPolicy=continue`). 그 단계는 실패 메모로 남고, 계산(calc)이 죽으면 그 요청은 실패한다.
- 멈추기: SIGTERM(`systemctl stop`)이면 받던 git·색인 자식 프로세스를 끝내고 `work/<jobId>`를 지운 뒤 종료 코드 143으로 끝난다. 유닛은 143을 성공으로 보므로(`SuccessExitStatus=143`) 멈춘 뒤 `failed`가 아니라 `inactive`로 남는다. 그 요청은 `running`으로 남고, 다음에 켤 때 위의 다시 시작 규칙으로 닫힌다.
- `--self-check`는 배포 때 지금 데이터 폴더로 돈다. 요청을 닫거나 고치지 않고, 결과(`OK` 또는 `자체 점검 실패: …`)만 stdout에 찍는다. git 판은 찍지 않는다(배포 출력이 공개 CI 로그에 남음).
