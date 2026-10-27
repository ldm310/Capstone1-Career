# job-skill — 채용공고 역량 추출

사람인의 IT 채용공고 가운데 **0~3년차가 지원할 수 있는 공고**를 모은다. 공고마다 필요한 역량(필수·우대·업무·기타)을 정해진 틀로 뽑아 DB에 넣는다.
뽑은 역량은 사용자 역량과 매칭하는 데 쓴다.

![파이프라인](docs/pipeline.png)

## 흐름

1. **수집 (Extract)**
   - 사람인 직무 목록(직무 코드)에서 공고를 받는다.
   - 목록의 경력 조건으로 최소 요구 연수 3년 이하만 남긴다. 교육생 공고는 뺀다.
2. **글로 바꾸기 (Transform)**
   - 글 공고: 본문 HTML에서 화면에 보이는 글만 쓴다(`html_text.py`).
   - 이미지 공고:
     - PaddleOCR로 글자와 좌표를 뽑는다.
     - 필요 없는 단락(회사 소개, 복리후생 등)을 낱말 규칙(rule base)으로 뺀다.
     - 표는 칸 순서대로 정리한다(`table_layout.py`).
3. **LLM 필요 정보 추출:** gpt-5.6-luna(reasoning low)가 처리한다. → [그림](docs/llm_extract.png)
   - 모집 단위(자리)를 나눈다: 직무별, 신입/경력별
   - 단위마다 필수 · 우대 · 업무 · 기타로 나눈다.
   - 줄마다 요건을 적는다: 능력 + 기술 + 관계(예시 / 택1 / 모두 / 능력만) + 근거
4. **기술 이름 표준화:** `capabilities.json` 사전으로 처리한다.
   - 별칭은 표준 이름으로 바꾼다.
   - 일반 낱말은 뺀다.
   - 사전에 없는 이름은 확인 필요로 표시한다.
5. **모집 단위 검사 (코드):** 의심되면 힌트를 붙여 LLM을 한 번 더 부른다. → [그림](docs/unit_check.png)
   1. 신입·경력을 빠짐없이 담았는가
   2. 모집 직무를 빠짐없이 담았는가
   3. IT 직무인데 내용이 비어 있지 않은가
6. **DB 저장 (Load):** PostgreSQL에 넣는다(`db_load.py`). → [ERD](docs/erd.png), [물리 설계](docs/physical-design.md)

## 파일

| 파일 | 내용 |
|---|---|
| `sample_random.py` | 수집: 사람인 직무 목록에서 0~3년 공고를 무작위로 뽑는다 → `<출력>/targets.tsv`, `pages/` |
| `sample_postings.py` | 수집(예전): 본문이 이미지뿐인 공고를 직무별로 고른다 |
| `fetch_images.py` | 공고 본문의 이미지를 받는다. 사람인 템플릿 이미지는 빼고, 받은 파일이 진짜 이미지인지 확인한다. |
| `common.py` | 공용 경로. 데이터 폴더는 환경변수 `OCR_DATA_DIR`로 고른다(예: `sample3`). |
| `html_text.py` | 글 공고: 보이는 글만, 표는 '■ 머리말' + 칸 글로 잇는다. |
| `run_paddle.py`, `dump_paddle_boxes.py` | PaddleOCR: 이미지 → 줄 상자 좌표와 글자 |
| `section_split.py` | 단락 나누기 + 필요 없는 단락 빼기(rule base). 파이프라인에서는 `--paddle-only`로 돌린다. |
| `table_layout.py` | OCR 상자를 표 구조대로 잇는다(왼쪽 머리말 표, 위쪽 머리말 열 표). |
| `extract_skills.py` | LLM 추출, 표준화, 모집 단위 검사. 브라우저 채점 화면 `out/extract/index.html`도 만든다. |
| `capabilities.json`, `capdict.py` | 표준화 사전(능력 61개, 기술 184개, 제외할 말)과 조회 코드. 사용자 역량도 같은 사전을 쓴다. |
| `db/schema.sql` | DB 표 만들기(PostgreSQL DDL). 설명은 [docs/physical-design.md](docs/physical-design.md) |
| `db_load.py` | DB 저장: 표 만들기(`init`), 사전 동기화(`sync-dict`), 공고·추출 결과 넣기(`load`). 여러 번 돌려도 겹치지 않는다. |
| `docker-compose.yml`, `.env.example` | 로컬 개발용 PostgreSQL(Docker). 비밀번호는 `.env`(올리지 않음) |
| `docs/` | 그림(파이프라인, 추출 방법, LLM 단계, 단위 검사, ERD), [물리 설계](docs/physical-design.md), [기술 스택 결정](docs/pipeline-stack.md), [OCR 비교 실험](docs/ocr-comparison.md) |
| `run_tesseract.py` 등 | OCR 비교 실험 코드 → [docs/ocr-comparison.md](docs/ocr-comparison.md) |

## 실행

준비
- Python 3.12에 `pillow`, `numpy`, `openai`, `psycopg[binary]`를 설치한다.
- PaddleOCR은 별도 가상환경에 설치한다(`requirements-paddle.txt`, GPU는 [OCR 비교 실험](docs/ocr-comparison.md#측정-환경) 참고).
- 환경변수 `OPENAI_API_KEY`를 설정한다(LLM).
- DB는 Docker로 띄운다: `.env.example`을 `.env`로 복사해 비밀번호를 정하고 `docker compose up -d`.
  PostgreSQL 17이 `localhost:5433`에 뜬다(내 컴퓨터에서만 접속). `db_load.py`는 `.env`의 `DATABASE_URL`을 읽는다.

```powershell
py -3.12 sample_random.py --out sample3 --per-role 10      # 1. 수집
$env:OCR_DATA_DIR = "sample3"
py -3.12 fetch_images.py                                  # 2. 이미지 받기
<venv-paddle>\Scripts\python.exe dump_paddle_boxes.py --gpu   # 3. OCR
py -3.12 section_split.py --paddle-only                   # 4. 단락 나누기·빼기
py -3.12 extract_skills.py --models gpt-5.6-luna --examples --tag -ex   # 5. LLM 추출·표준화·단위 검사 (유료)
py -3.12 db_load.py init                                  # 6. DB: 표 만들기 (처음 한 번)
py -3.12 db_load.py sync-dict                             #    사전 넣기 (사전을 고칠 때마다)
py -3.12 db_load.py load --run gpt-5.6-luna-ex            #    공고·추출 결과 넣기
```

비용은 공고당 약 $0.004다(luna low, 다시 부르기 포함).
`--examples`는 프롬프트에 예시 답안을 붙인다(지금 쓰는 설정). `--tag`는 결과 폴더 이름 뒤에 붙는다(`out/extract/gpt-5.6-luna-ex/`).
추출 결과에는 표준화 전 답, 확인 필요 사유(`[{검사, 내용}]`), 프롬프트·사전 버전, 입력 해시, 비용이 함께 저장된다.

## 데이터 원칙

- 받은 이미지, 공고 본문, OCR 글자, 추출 결과, 샘플 목록은 **저장소에 올리지 않는다**(`.gitignore`). 외부에 다시 게시하지 않는다.
- 사람인에는 요청을 초당 1건 이하(간격 1.2초)로 보낸다. User-Agent는 브라우저로 꾸미지 않고 프로젝트 이름을 넣는다.
- API 키는 코드에 넣지 않고 환경변수로만 쓴다.
