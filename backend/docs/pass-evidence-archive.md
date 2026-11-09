# 공고 연결 전 합격자료 보관함

현재 공고 회사와 엄격한 단일 IT 직무 조건을 통과한 자료만 서비스 DB에 넣던 방식은 자료 확보량을 제한한다. `evidence_archive`는 공개 출처의 본문을 먼저 보관하고 회사 ID 매핑·직무 정리·근거 추출을 이후에 수행한다. 기존 서비스 DB와 읽기 API에 자동 반영하지 않는다.

## 출처와 신뢰 상태

| 출처 | 확보 내용 | 기록하는 한계 |
|---|---|---|
| 잡코리아 공식 합격자소서 | 목록의 회사·직무·시즌과 상세의 질문·답변 | 플랫폼 게시물이며 개별 최종합격 검증 완료를 의미하지 않음 |
| 링커리어 공식 합격자소서 | 공개 검색·상세의 회사·직무·본문 | 공개 원문에 없는 합격 단계·평가 수준을 추정하지 않음 |
| 인천대학교 공식 취업수기집 | 정보기술대학·생명과학기술대학 PDF 원본과 페이지별 텍스트 | 취업·현장실습·소개 페이지가 섞여 있으며 한 페이지를 한 합격자로 세지 않음 |

검토한 대학 원문 게시글:

- [정보기술대학 취업성공 및 현장실습 수기](https://www.inu.ac.kr/bbs/ese/917/404805/artclView.do)
- [생명과학기술대학 졸업생 취업 수기](https://www.inu.ac.kr/bbs/molbio/1884/404816/artclView.do)

사람인의 확인된 자소서 작성 링크는 로그인으로 이동했다. 렛유인 공식 메뉴가 연결하는 이공모야 후기는 공개 목록은 확인했지만 이번 확인에서 본문 영역을 안정적으로 추출하지 못했다. 이 출처의 안내문·로그인 화면·빈 본문을 확보 건수로 세지 않는다. 신뢰도가 높은 신규 출처도 실제 본문과 열람 정책 확인 후 추가한다.

## 실행

Python 3.12 이상과 `data-pipeline/external-pass-crawler/requirements.txt` 의존성을 준비한다. 해당 패키지 경로를 PYTHONPATH로 지정하거나 패키지 디렉터리에서 실행한다.

```powershell
# 출처당 신규 상세 최대 200회. 기존 자료는 상세 재요청 없이 재사용.
python -m external_pass_crawler.evidence_archive --output ../../work/pass-evidence-archive --sources jobkorea linkareer --max-documents 200 --max-pages 30

# 개발·데이터 직무 집중 확보. 이미 받은 비IT 자료는 보존.
python -m external_pass_crawler.evidence_archive --output ../../work/pass-evidence-archive --sources jobkorea --jobkorea-keywords 소프트웨어 웹개발 데이터 서버 모바일 정보보안 --it-only --max-documents 100 --max-pages 30

# 검토한 공식 대학 출판물만 PDF 원본과 페이지 텍스트로 확보.
python -m external_pass_crawler.university_archive --output ../../work/pass-evidence-university
```

예시 상대 경로는 `data-pipeline/external-pass-crawler`에서 실행할 때 기준이다. 출력 경로는 실제 실행 디렉터리를 기준으로 확인한다. 배포된 회사별 일일 CLI와 별개이며 이 명령들은 RDS 연결 정보가 필요 없다. 자동 일일 실행·무제한 백그라운드 작업을 설치하지 않는다.

최소 2초 간격, robots crawl-delay 우선, robots 허용 확인, 동일 출처 허용 목록, 크기·페이지·문서 상한을 적용한다. 401/403/429·CAPTCHA·리다이렉트·robots 제한은 해당 출처 중단으로 처리한다. 접근 제한은 아카이브 DB의 `source_block`에 남아 다음 실행에도 자동 재시도하지 않는다. 운영자가 원인을 확인하기 전에 해당 행을 삭제하거나 다른 출력 폴더를 만들어 재접근하지 않는다. 같은 출처를 처리하는 다른 수집기와 동시에 실행하지 않는다.

## 결과 파일

| 파일 | 내용 |
|---|---|
| `archive.sqlite3` | 출처+원문 ID 고유 문서, 수집 메타데이터와 접근 차단 상태 |
| `manifest.jsonl` | 문서별 출처 URL·회사·직무·본문 경로·해시·수집 시각·검증 상태 |
| `catalog.csv` | Excel에서 볼 수 있는 UTF-8 BOM 메타데이터 목록 |
| `bodies/<sha256>.txt` | HTML을 제거하고 직접 연락처 등을 마스킹한 본문 |
| `images/<sha256>.*` | 본문 내부의 허용 출처 이미지가 있는 경우만 보관. OCR은 PENDING |
| `last-run.json` | 이번 실행의 출처별 성공·재사용·실패·상한·차단 집계 |
| 대학 `*.pdf` | 공식 출판물 원본. 이미지와 페이지 구성을 보존 |
| 대학 `*.pages.jsonl` | 원본 페이지 번호와 텍스트, TEXT_READY/OCR_PENDING |
| 대학 `manifest.json` | 출판물별 원문 게시글·다운로드 URL·SHA-256·쪽 수·추출 상태 |

문서 ID가 같으면 상세를 다시 받지 않는다. 본문이 완전히 같으면 SHA-256 파일을 공유하지만 원문별 메타데이터는 보존한다. 서로 다른 글·문항·사이트에 같은 작성자가 있어도 개인 신원을 추정해 합치지 않는다. 문서 수·고유 본문 수·합격자 수를 구분한다.

신규 문서는 `company_id=null`, `extraction_status=PENDING`, `identity_verified=false`, `final_pass_verified=false`다. 플랫폼 합격자소서는 전형이 명시되지 않으면 `pass_stage=UNSPECIFIED`다. 기술 언급을 점수나 LV로 바꾸지 않는다. `standard_role_code`가 null이어도 전체 수집 모드에서는 본문을 보존한다.

보관함은 `work/` 아래에 두어 커밋·API·일반 로그에 본문을 노출하지 않는다. 텍스트의 직접 연락처·식별번호 마스킹은 완전한 익명화가 아니다. 대학 PDF 원본과 이미지에는 작성자가 공개한 이름·사진·학교·경력 등이 남을 수 있다. 회사·직무별 서비스 연결 전에 사례 분리·개인정보 검토·중복 검토를 수행한다. robots 허용 여부를 재배포·학습 사용 허가로 해석하지 않는다.

현재 범위는 원자료 확보다. 이미지 OCR·사례별 분리·합격 인증·서비스 DB 적재·프론트 차트 연결은 별도 단계다. 유료 OCR·임베딩 API는 호출하지 않는다.
