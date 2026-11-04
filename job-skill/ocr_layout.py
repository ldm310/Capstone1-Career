"""EasyOCR·PaddleOCR 공용: 세로 분할, 조각 결과 병합, 글자 상자 -> 줄 단위 텍스트.

두 엔진 모두 검출 단계에서 이미지의 긴 변을 줄인다(EasyOCR canvas_size=2560, PaddleOCR 최대 4000).
세로 20,000px 이미지를 통째로 넣으면 글자가 몇 px 로 줄어 검출이 안 되므로
높이 TILE_H, 겹침 OVERLAP 으로 잘라 넣고, 겹친 구간의 중복은 '상자 중심이 조각의 몫(core) 안에 있는 것만 채택'
규칙으로 없앤다. 줄 높이 < OVERLAP 이면 모든 줄이 정확히 한 조각에서만 채택된다.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from common import tile_spans

TILE_H = 2000
OVERLAP = 300


def load_rgb(path: str) -> np.ndarray:
    """경로에 한글이 있어도 읽히도록 PIL 로 연다(cv2.imread 는 윈도우 한글 경로를 못 읽는다)."""
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def tiled_boxes(img: np.ndarray, ocr_tile) -> list[tuple[float, float, float, float, str]]:
    """ocr_tile(tile_rgb) -> [(x1, y1, x2, y2, text)] 를 조각마다 불러 원본 좌표로 합친다."""
    h = img.shape[0]
    spans = tile_spans(h, TILE_H, OVERLAP)
    out = []
    for i, (y0, y1) in enumerate(spans):
        lo = 0 if i == 0 else (spans[i - 1][1] + y0) / 2          # 앞 조각과 겹친 구간의 가운데
        hi = h if i == len(spans) - 1 else (y1 + spans[i + 1][0]) / 2
        for x1, by1, x2, by2, text in ocr_tile(img[y0:y1]):
            cy = y0 + (by1 + by2) / 2
            if lo <= cy < hi:
                out.append((x1, y0 + by1, x2, y0 + by2, text))
    return out


def boxes_to_text(boxes: list[tuple[float, float, float, float, str]]) -> str:
    """상자를 줄로 묶는다: 위에서부터 보며 현재 줄과 세로로 절반 이상 겹치면 같은 줄,
    줄 안에서는 왼쪽부터 공백으로 잇는다. (2단 배치는 좌우가 한 줄로 섞일 수 있다 — 엔진 기본 출력의 한계)"""
    boxes = sorted((b for b in boxes if b[4].strip()), key=lambda b: (b[1] + b[3]) / 2)
    lines: list[dict] = []
    for b in boxes:
        x1, y1, x2, y2, text = b
        bh = max(1.0, y2 - y1)
        if lines:
            cur = lines[-1]
            ov = min(y2, cur["y2"]) - max(y1, cur["y1"])
            if ov >= 0.5 * min(bh, cur["y2"] - cur["y1"]):
                cur["items"].append(b)
                cur["y1"], cur["y2"] = min(cur["y1"], y1), max(cur["y2"], y2)
                continue
        lines.append({"y1": y1, "y2": y2, "items": [b]})
    return "\n".join(" ".join(it[4].strip() for it in sorted(ln["items"], key=lambda it: it[0]))
                     for ln in lines)
