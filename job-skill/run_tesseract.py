"""
2단계 후보 A-1: Tesseract (-l kor+eng, tessdata_best).

  - 모델: models/tessdata/ 의 tessdata_best kor/eng (fetch 는 README 참고). 설치본 tessdata 는 쓰지 않는다.
  - 설정: 기본값(--oem 기본, --psm 3). 전처리·확대 없음. 원본 이미지를 통째로 넣는다
    (Tesseract 는 내부에서 이미지를 줄이지 않으므로 자르지 않는다).
  - 이미지는 stdin 으로 넘긴다(경로의 한글 처리 문제 회피).
  - 시간: 이미지 1장당 프로세스 시작·모델 로드를 포함한 벽시계 시간.

실행: py -3.12 run_tesseract.py
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import time

from common import HERE, IMG_DIR, OUT_DIR, images_by_posting, write_text

CAND = "tesseract"
EXE = os.environ.get("TESSERACT_EXE", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSDATA = os.path.join(HERE, "models", "tessdata")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def ocr(path: str) -> tuple[str, float]:
    with open(path, "rb") as f:
        data = f.read()
    t0 = time.perf_counter()
    r = subprocess.run([EXE, "stdin", "stdout", "-l", "kor+eng", "--tessdata-dir", TESSDATA],
                       input=data, capture_output=True)
    sec = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace"))
    return r.stdout.decode("utf-8", "replace"), sec


def main() -> None:
    ver = subprocess.run([EXE, "--version"], capture_output=True).stdout.decode().splitlines()[0]
    print(ver, "| tessdata:", TESSDATA)
    timing = []
    for rid, imgs in images_by_posting().items():
        parts = []
        for im in imgs:
            text, sec = ocr(os.path.join(IMG_DIR, im["file"]))
            parts.append(text.strip())
            timing.append({"rec_idx": rid, "seq": im["seq"], "file": im["file"], "width": im["width"],
                           "height": im["height"], "seconds": f"{sec:.2f}"})
            print(f"  {im['file']:<20} {im['width']:>5}x{im['height']:<6} {sec:6.1f}s  {len(text):>6}자")
        write_text(CAND, rid, "\n\n".join(parts) + "\n")

    with open(os.path.join(OUT_DIR, CAND, "_timing.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(timing[0]), delimiter="\t")
        w.writeheader()
        w.writerows(timing)
    total = sum(float(t["seconds"]) for t in timing)
    print(f"이미지 {len(timing)}장, 합계 {total:.1f}s, 평균 {total / len(timing):.1f}s/장")


if __name__ == "__main__":
    main()
