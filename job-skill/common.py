"""OCR 비교 테스트 공용 경로·도우미 (표준 라이브러리만 사용)."""

from __future__ import annotations

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# 데이터 폴더(targets.tsv, images/, pages/, out/). 기본은 이 폴더, 새 샘플은 환경변수로 바꾼다: OCR_DATA_DIR=sample2
DATA = os.path.join(HERE, os.environ.get("OCR_DATA_DIR", "")) if os.environ.get("OCR_DATA_DIR") else HERE
IMG_DIR = os.path.join(DATA, "images")
PAGE_DIR = os.path.join(DATA, "pages")
OUT_DIR = os.path.join(DATA, "out")
MANIFEST = os.path.join(IMG_DIR, "manifest.tsv")


def load_targets() -> list[dict]:
    with open(os.path.join(DATA, "targets.tsv"), encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def load_manifest() -> list[dict]:
    """images/manifest.tsv -> 공고 순서·이미지 순번 순으로 정렬된 행 목록."""
    with open(MANIFEST, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    order = {t["rec_idx"]: i for i, t in enumerate(load_targets())}
    rows.sort(key=lambda r: (order[r["rec_idx"]], int(r["seq"])))
    return rows


def images_by_posting() -> dict[str, list[dict]]:
    """{rec_idx: [manifest 행, ...]} — 이미지를 받은 공고만, targets.tsv 순서."""
    out: dict[str, list[dict]] = {}
    for r in load_manifest():
        if not r.get("file"):  # 받기에 실패한 이미지(404·이미지 아님 등)는 파일이 없다 — OCR·화면에서 빼야 함
            continue
        out.setdefault(r["rec_idx"], []).append(r)
    return out


def tile_spans(height: int, tile_h: int, overlap: int) -> list[tuple[int, int]]:
    """세로 [0, height)를 높이 tile_h, 겹침 overlap 으로 자른 (y0, y1) 목록.
    마지막 조각은 아래 끝에 맞춘다(짧은 자투리 조각을 만들지 않는다)."""
    if height <= tile_h:
        return [(0, height)]
    step = tile_h - overlap
    spans, y = [], 0
    while y + tile_h < height:
        spans.append((y, y + tile_h))
        y += step
    spans.append((max(0, height - tile_h), height))
    return spans


def write_text(candidate: str, rec_idx: str, text: str) -> str:
    d = os.path.join(OUT_DIR, candidate)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{rec_idx}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
