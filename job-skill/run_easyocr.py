"""
2단계 후보 A-2: EasyOCR (['ko', 'en']).

  - 설정: Reader(['ko', 'en'], gpu=GPU), readtext 기본값(detail=1, paragraph=False). 전처리 없음.
  - 세로로 긴 이미지는 ocr_layout.TILE_H/OVERLAP 으로 잘라 넣고 병합한다(검출 단계 축소 회피).
  - 시간: 모델 로드·워밍업을 뺀, 이미지 1장 처리(분할·인식·병합)의 벽시계 시간.

실행: <venv-easyocr>/Scripts/python.exe run_easyocr.py [--gpu]
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import numpy as np

from common import IMG_DIR, OUT_DIR, images_by_posting, write_text
from ocr_layout import OVERLAP, TILE_H, boxes_to_text, load_rgb, tiled_boxes

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", action="store_true")
    args = ap.parse_args()
    cand = "easyocr_gpu" if args.gpu else "easyocr"

    import easyocr
    import torch

    t0 = time.perf_counter()
    reader = easyocr.Reader(["ko", "en"], gpu=args.gpu, verbose=False)
    reader.readtext(np.full((64, 256, 3), 255, np.uint8))  # 워밍업
    load_sec = time.perf_counter() - t0
    print(f"easyocr {easyocr.__version__} | torch {torch.__version__} | gpu={args.gpu} | "
          f"threads={torch.get_num_threads()} | 로드 {load_sec:.1f}s | tile {TILE_H}/{OVERLAP}")

    def ocr_tile(tile: np.ndarray):
        res = reader.readtext(tile)
        return [(min(p[0] for p in box), min(p[1] for p in box), max(p[0] for p in box),
                 max(p[1] for p in box), text) for box, text, _conf in res]

    timing = []
    for rid, imgs in images_by_posting().items():
        parts = []
        for im in imgs:
            img = load_rgb(os.path.join(IMG_DIR, im["file"]))
            t = time.perf_counter()
            text = boxes_to_text(tiled_boxes(img, ocr_tile))
            sec = time.perf_counter() - t
            parts.append(text)
            timing.append({"rec_idx": rid, "seq": im["seq"], "file": im["file"], "width": im["width"],
                           "height": im["height"], "seconds": f"{sec:.2f}"})
            print(f"  {im['file']:<20} {im['width']:>5}x{im['height']:<6} {sec:6.1f}s  {len(text):>6}자", flush=True)
        write_text(cand, rid, "\n\n".join(parts) + "\n")

    with open(os.path.join(OUT_DIR, cand, "_timing.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(timing[0]), delimiter="\t")
        w.writeheader()
        w.writerows(timing)
    total = sum(float(t["seconds"]) for t in timing)
    print(f"이미지 {len(timing)}장, 합계 {total:.1f}s, 평균 {total / len(timing):.1f}s/장 (모델 로드 {load_sec:.1f}s 별도)")


if __name__ == "__main__":
    main()
