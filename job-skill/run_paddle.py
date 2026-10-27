"""
2단계 후보 A-3: PaddleOCR (lang='korean', PP-OCRv5 한국어 인식 모델).

  - 설정: PaddleOCR(lang='korean', device=cpu) — 문서 방향 분류·문서 펴기(unwarping)·줄 방향 분류는 끈다
    (촬영 문서용 기능이라 디지털 공고 이미지에는 불필요하고, unwarping 은 이미지를 변형한다). 그 외 기본값.
  - 세로로 긴 이미지는 ocr_layout.TILE_H/OVERLAP 으로 잘라 넣고 병합한다(검출 단계 최대 4000px 축소 회피).
  - 시간: 모델 로드·워밍업을 뺀, 이미지 1장 처리(분할·인식·병합)의 벽시계 시간.
  - --gpu: GPU(device=gpu:0)로 실행하고 out/paddleocr_gpu/ 에 쓴다. paddlepaddle-gpu 가 깔린 환경에서 실행.

실행: <venv-paddle>/Scripts/python.exe run_paddle.py [--gpu]
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
    CAND = "paddleocr_gpu" if args.gpu else "paddleocr"
    device = "gpu:0" if args.gpu else "cpu"

    import paddle
    import paddleocr
    from paddleocr import PaddleOCR

    t0 = time.perf_counter()
    ocr = PaddleOCR(lang="korean", device=device,
                    use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False)
    warm = np.full((64, 256, 3), 255, np.uint8)
    list(ocr.predict(warm))  # 워밍업
    load_sec = time.perf_counter() - t0
    print(f"paddleocr {paddleocr.__version__} | paddle {paddle.__version__} | device {device} | 로드 {load_sec:.1f}s | "
          f"tile {TILE_H}/{OVERLAP}")

    models_logged = []

    def ocr_tile(tile: np.ndarray):
        # PaddleOCR 는 BGR 입력을 기대한다.
        res = list(ocr.predict(np.ascontiguousarray(tile[:, :, ::-1])))[0]
        if not models_logged:
            models_logged.append(1)
            cfg = res.get("model_settings", {})
            print("  model_settings:", cfg)
        boxes = res["rec_boxes"]
        return [(float(b[0]), float(b[1]), float(b[2]), float(b[3]), t)
                for b, t in zip(boxes, res["rec_texts"])]

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
        write_text(CAND, rid, "\n\n".join(parts) + "\n")

    with open(os.path.join(OUT_DIR, CAND, "_timing.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(timing[0]), delimiter="\t")
        w.writeheader()
        w.writerows(timing)
    total = sum(float(t["seconds"]) for t in timing)
    print(f"이미지 {len(timing)}장, 합계 {total:.1f}s, 평균 {total / len(timing):.1f}s/장 (모델 로드 {load_sec:.1f}s 별도)")


if __name__ == "__main__":
    main()
