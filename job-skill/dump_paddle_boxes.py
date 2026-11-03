"""
PaddleOCR 로 이미지 전체의 줄 상자 좌표와 글자를 뽑아 out/page_filter/paddle_boxes/<이미지>.json 에 저장한다.
설정은 run_paddle.py 와 같다(2000px/겹침 300 분할, 겹친 구간은 상자 중심으로 한 번만 채택). 단락 나누기의 위치 찾기용.

실행: <venv-paddle>/Scripts/python.exe dump_paddle_boxes.py
"""

from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

from common import IMG_DIR, OUT_DIR, images_by_posting
from ocr_layout import load_rgb, tiled_boxes

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", action="store_true", help="GPU(paddlepaddle-gpu 환경)로 실행")
    args = ap.parse_args()
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(lang="korean", device="gpu:0" if args.gpu else "cpu", use_doc_orientation_classify=False,
                    use_doc_unwarping=False, use_textline_orientation=False)
    list(ocr.predict(np.full((64, 256, 3), 255, np.uint8)))

    def ocr_tile(tile):
        res = list(ocr.predict(np.ascontiguousarray(tile[:, :, ::-1])))[0]
        return [(float(b[0]), float(b[1]), float(b[2]), float(b[3]), t) for b, t in zip(res["rec_boxes"], res["rec_texts"])]

    d = os.path.join(OUT_DIR, "page_filter", "paddle_boxes")
    os.makedirs(d, exist_ok=True)
    timing = {}
    for imgs in images_by_posting().values():
        for im in imgs:
            t = time.perf_counter()
            boxes = tiled_boxes(load_rgb(os.path.join(IMG_DIR, im["file"])), ocr_tile)
            timing[im["file"]] = round(time.perf_counter() - t, 2)
            with open(os.path.join(d, os.path.splitext(im["file"])[0] + ".json"), "w", encoding="utf-8") as f:
                json.dump([[round(x1), round(y1), round(x2), round(y2), s] for x1, y1, x2, y2, s in boxes], f, ensure_ascii=False)
            print(f"  {im['file']:<20} 상자 {len(boxes):>4}개 {timing[im['file']]:6.1f}s", flush=True)
    with open(os.path.join(d, "_timing.json"), "w", encoding="utf-8") as f:
        json.dump(timing, f)


if __name__ == "__main__":
    main()
