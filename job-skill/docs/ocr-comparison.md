# OCR 비교 실험 (2026-10-02 ~ 10-10)

사람인의 이미지 전용 공고 10건을 글자로 바꾸는 방법을 비교했다. 후보는 A(전용 OCR)와 B(이미지를 읽는 LLM)다.
결론은 **PaddleOCR**이다. 근거는 아래 정확도 시험이다.

## 정확도 시험 (2026-10-10)

- 대상: 첫 샘플의 15구간, 약 320줄
- 정답: Claude가 이미지를 보고 받아 적었다.
- 결과 원본: `out/ocr_accuracy/` (로컬 전용, 공고 글자가 담겨 있어 올리지 않는다)

| 방식 | 글자 정확도 | 종합(순서 포함) |
|---|---|---|
| Tesseract | 81% | 70% |
| EasyOCR (CPU) | 92% | 85% |
| PaddleOCR | 100% | 92% |
| PaddleOCR + 표 정리 (`table_layout.py`) | 100% | 98% |
| LLM(gpt-5.6-terra) 받아쓰기 | 100% | 100% |

PaddleOCR을 고른 그 밖의 이유는 세 가지다.
- 속도: GPU로 이미지당 2.3초 (CPU 37초, EasyOCR CPU 69초, Tesseract 14초)
- 비용: 무료 (로컬 실행)
- 표 정리: 줄 좌표를 줘서 단락 나누기와 표 정리를 할 수 있다.

LLM 받아쓰기는 정확하지만 좌표가 없고 돈이 든다.

## 실험 코드

| 파일 | 내용 |
|---|---|
| `run_tesseract.py` / `run_easyocr.py` / `run_paddle.py` / `run_llm.py` | 후보별로 `out/{후보}/{rec_idx}.txt`와 `_timing.tsv`를 만든다. |
| `ocr_layout.py` | EasyOCR·PaddleOCR 공용: 세로 분할, 병합, 줄 묶기 |
| `evaluate.py` | 스킬 단위 평가(정답표 `truth.tsv` 검수가 필요해 보류) |
| `page_filter_sim.py` | '필요 없는 페이지 빼기' 모의 실험 |
| `build_viewer.py` | 후보별 OCR 글자를 한곳에 모은 보기 파일 |

`section_split.py`(파이프라인)가 `page_filter_sim.py`, `evaluate.py`, `run_llm.py`의 함수 일부를 가져다 쓴다. 그래서 이 파일들은 지우거나 옮기지 않는다.

## 측정 환경

- Windows 11. 기본은 CPU 실행이고, PaddleOCR만 GPU(RTX 3060 Laptop 6GB)로도 측정했다.
  - 별도 가상환경에 `paddlepaddle-gpu==3.2.2`(`-i https://www.paddlepaddle.org.cn/packages/stable/cu126/`) + `paddleocr==3.7.0`를 설치했다.
  - `run_paddle.py --gpu` → `out/paddleocr_gpu/`. 이미지당 평균 2.3초(CPU 26.7~36.7초).
  - CPU와 GPU의 글자는 10건 중 7건 같았고, 나머지도 99.94% 이상 일치했다.
- Tesseract 5.5.0 (`C:\Program Files\Tesseract-OCR`). 언어 데이터는 `models/tessdata/`의 tessdata_best `kor`·`eng`이다(로컬 전용, 다시 받기):
  ```
  curl -L -o models/tessdata/kor.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/kor.traineddata
  curl -L -o models/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata
  ```
- EasyOCR: Python 3.12 가상환경, `requirements-easyocr.txt` (easyocr 1.7.2, torch 2.14.1 CPU)
- PaddleOCR: Python 3.12 가상환경, `requirements-paddle.txt` (paddleocr 3.7.0, **paddlepaddle 3.2.2**)
  - 최신 paddlepaddle 3.3.1은 이 PC(Windows CPU)에서 oneDNN 경로 오류(`NotImplementedError: ConvertPirAttribute2RuntimeAttribute …`)로 실행되지 않았다.
  - `enable_mkldnn=False`로 끄면 돌지만 같은 이미지가 75초 걸렸다(3.2.2 + oneDNN은 7초). 속도를 대표하지 못해 3.2.2를 썼다. 글자 결과는 같았다.
- LLM: OpenAI `gpt-5.6-terra` (Responses API, `detail="high"`, reasoning effort `none`), 환경변수 `OPENAI_API_KEY`
- 유료 OCR API: 키가 없어 건너뛰었다.

## 실행 순서

```
py -3.12 fetch_images.py
py -3.12 run_tesseract.py
<venv-easyocr>\Scripts\python.exe run_easyocr.py
<venv-paddle>\Scripts\python.exe run_paddle.py
py -3.12 run_llm.py --model gpt-5.6-terra      # 끊기면 다시 실행: _calls.jsonl 에 있는 조각은 건너뛴다
py -3.12 evaluate.py                            # truth.tsv 검수 후
```

## 자른 기준

| 후보 | 자르는 경우 | 조각 높이 | 겹침 | 겹친 구간 중복 처리 |
|---|---|---|---|---|
| Tesseract | 자르지 않음(내부에서 축소하지 않는다) | – | – | – |
| EasyOCR·PaddleOCR | 높이 2,000px 초과 | 2,000px | 300px | 글자 상자 중심이 겹침 구간 가운데선 기준 자기 몫에 있는 것만 채택 |
| LLM | 세로 > 가로×2 | 가로×1.5 | 가로×0.15 (최소 100px) | 지시문으로 가장자리에서 잘린 줄은 빼게 하고, 앞 조각 끝·다음 조각 처음 줄이 겹치면 한 번만 남김 |

## 시간 재는 법

- Tesseract: 이미지 1장마다 프로세스 시작과 모델 로드를 포함한 벽시계 시간(pytesseract 쓰임새와 같다).
- EasyOCR·PaddleOCR: 모델 로드·워밍업 1회를 뺀 이미지 1장 처리(분할·인식·병합) 시간. 기본 스레드 설정.
- LLM: API 왕복 시간만 쟀다(이미지 인코딩 제외).
- LLM 실행이 Tesseract·EasyOCR 실행과 시간대가 겹쳤다(PaddleOCR은 단독).
  - Tesseract를 단독으로 다시 돌려 보니 장당 평균 3.5% 빨랐고(14.4→13.9초, 장별 0~8%) 글자 결과는 같았다.
  - `out/tesseract/_timing.tsv`는 단독 실행, `_timing_concurrent.tsv`는 동시 실행 값이다.
  - EasyOCR 값은 동시 실행 값이라 몇 % 부풀었을 수 있다.
