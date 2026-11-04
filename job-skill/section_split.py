"""
단락 나누기 + '필요 없는 단락 빼기' + LLM 입력 묶음 만들기 (로컬 전용, LLM 호출 없음).

  1) 위치 찾기 OCR 로 이미지 전체를 한 번 읽어 좌표를 얻는다. 두 가지를 비교한다:
     Tesseract(단어 좌표, out/page_filter/tsv/) / PaddleOCR(줄 상자, dump_paddle_boxes.py -> out/page_filter/paddle_boxes/).
     낱말 찾기는 공백을 무시한다(Tesseract 가 전체 이미지에서 한글을 음절마다 띄어 쓰는 문제).
     뺀 단락은 다른 OCR 글자로 다시 판정해, 남길 낱말·기술명이 보이면 경고를 붙인다.
  2) 머리말 줄을 찾는다: 머리말 낱말이 있는 짧은 줄(공백 뺀 30자 이하) 또는 본문보다 1.35배 이상 큰 짧은 줄.
  3) 머리말 바로 위에서 자른다. 우선순위: 한 가지 색으로 된 빈 줄 > 글자 상자가 걸리지 않고 거의 빈 줄 > 글자 상자만 피한 줄.
     자를 곳이 없거나 앞 단락이 2줄 미만이면 자르지 않는다. 글자 줄은 절대 자르지 않으므로 겹침이 필요 없다.
  4) 단락마다 판정(page_filter_sim.decide 와 같은 낱말 목록). 요건 낱말·기술명이 있으면 글자가 적어도 남긴다.
  5) 남긴 단락 중 이웃한 것을 높이 1.5W 안에서 묶어 LLM 입력 묶음을 만든다. 넘치는 단락은 단락 안의 빈 줄에서 나눈다.

비교: 기존 고정 조각(1.5W/겹침 0.15W)에도 같은 판정 규칙을 적용해 나란히 센다. 비용은 기존 LLM 실측 토큰으로 맞춘 추정치.
결과: out/page_filter/sections.html, sections.json, sec/*.jpg, map/*.jpg
실행: py -3.12 section_split.py
"""

from __future__ import annotations

import csv
import html
import io
import json
import math
import os
import re
import subprocess
import sys
from collections import defaultdict

import numpy as np
from PIL import Image

from common import IMG_DIR, OUT_DIR, images_by_posting, load_targets
from page_filter_sim import DROP, EXE, KEEP, LLM, PF, TESSDATA, highlight, tech_spans
from table_layout import table_zones
from run_llm import tiles_for

HDR = re.compile(r"자격\s*요건|지원\s*자격|필수|우대|요건|requirement|preferred|qualification|담당\s*업무|주요\s*업무|업무\s*내용|"
                 r"하게\s*될|기술\s*스택|사용하는\s*기술|tech\s*stack|모집\s*부문|모집\s*분야|이런\s*분|함께\s*하고\s*싶|좋아요|"
                 r"알고\s*계시면|복리\s*후생|복지|전형\s*절차|채용\s*절차|전형\s*안내|지원\s*방법|접수\s*방법|제출\s*서류|근무\s*조건|"
                 r"근무\s*형태|유의\s*사항|회사\s*소개|연혁|일하는\s*방식|근무지|지원\s*기간|접수\s*기간|채용\s*조건|채용\s*전형", re.I)
PRICE_IN, PRICE_OUT = 2.00, 12.00  # gpt-5.6-terra, USD / 1M 토큰

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- 판정 (기존 조각과 공통)

def flat(text: str) -> str:
    """낱말 찾기용: 공백을 모두 뺀다. Tesseract 가 이미지 전체를 읽을 때 한글을 음절마다 띄어 쓰는 문제(자 격 요 건) 대응."""
    return re.sub(r"\s+", "", text)


def decide(text: str) -> dict:
    f = flat(text)
    keep = list(dict.fromkeys(m.group(0) for m in KEEP.finditer(f)))
    drop = list(dict.fromkeys(m.group(0) for m in DROP.finditer(f)))
    techs = sorted({text[a:b] for a, b in tech_spans(text)}, key=str.lower)
    n = len(f)
    if keep or techs:
        d, why = "남기기", "요건 낱말·기술명 있음"
    elif n < 30:
        d, why = "빼기", "글자 거의 없음"
    elif drop:
        d, why = "빼기", "복지·절차·조건 낱말만 있음"
    else:
        d, why = "남기기", "애매(어느 낱말도 없음)"
    return {"decision": d, "reason": why, "keep": keep, "drop": drop, "tech": techs, "chars": n,
            "mixed": bool(drop and (keep or techs))}


# ---------------------------------------------------------------- Tesseract 좌표

def tess_words(stem: str, img: Image.Image) -> list[dict]:
    path = os.path.join(PF, "tsv", stem + ".tsv")
    if not os.path.exists(path):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        r = subprocess.run([EXE, "stdin", "stdout", "-l", "kor+eng", "--tessdata-dir", TESSDATA, "-c", "tessedit_create_tsv=1"],
                           input=buf.getvalue(), capture_output=True)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").write(r.stdout.decode("utf-8", "replace"))
    words = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if r.get("level") == "5" and (r.get("text") or "").strip():
                words.append({"key": (r["block_num"], r["par_num"], r["line_num"]), "x": int(r["left"]),
                              "y": int(r["top"]), "w": int(r["width"]), "h": int(r["height"]), "text": r["text"]})
    return words


def lines_of(words: list[dict]) -> list[dict]:
    g = defaultdict(list)
    for w in words:
        g[w["key"]].append(w)
    lines = []
    for ws in g.values():
        ws.sort(key=lambda w: w["x"])
        lines.append({"y0": min(w["y"] for w in ws), "y1": max(w["y"] + w["h"] for w in ws),
                      "x0": min(w["x"] for w in ws), "text": " ".join(w["text"] for w in ws),
                      "h": float(np.median([w["h"] for w in ws]))})
    lines.sort(key=lambda l: (l["y0"], l["x0"]))
    return lines


# ---------------------------------------------------------------- 자를 위치

def row_stats(img: Image.Image, words: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    g = np.asarray(img.convert("L"), dtype=np.float32)
    std = g.std(axis=1)
    covered = np.zeros(g.shape[0], bool)
    for w in words:
        covered[max(0, w["y"] - 2):w["y"] + w["h"] + 2] = True
    return std, covered


def best_cut(lo: int, hi: int, std: np.ndarray, covered: np.ndarray, prefer: int) -> tuple[int | None, str]:
    """[lo, hi) 안에서 자를 줄. 빈 줄(표준편차<4) > 글자 상자 없고 거의 빈 줄(<20) > 글자 상자만 피한 줄."""
    if hi - lo < 1:
        return None, ""
    for kind, mask in (("빈 줄", (std[lo:hi] < 4) & ~covered[lo:hi]),
                       ("거의 빈 줄", (std[lo:hi] < 20) & ~covered[lo:hi]),
                       ("글자 사이", ~covered[lo:hi])):
        runs, start = [], None
        for i, m in enumerate(list(mask) + [False]):
            if m and start is None:
                start = i
            elif not m and start is not None:
                runs.append((lo + start, lo + i))
                start = None
        if runs:
            a, b = min(runs, key=lambda r: (-(r[1] - r[0]) // 4, abs((r[0] + r[1]) // 2 - prefer)))
            return (a + b) // 2, kind
    return None, ""


def is_header(line: dict, median_h: float) -> bool:
    f = flat(line["text"])
    if len(f) < 2:
        return False
    return (len(f) <= 30 and bool(HDR.search(f))) or (len(f) <= 25 and line["h"] >= 1.35 * median_h)


def split_sections(img: Image.Image, words: list[dict]) -> list[dict]:
    h = img.height
    lines = lines_of(words)
    std, covered = row_stats(img, words)
    median_h = float(np.median([l["h"] for l in lines])) if lines else 0
    min_h = max(60, round(0.08 * img.width))  # 이보다 짧은 단락은 만들지 않는다
    # 표('왼쪽 머리말 | 오른쪽 내용')로 인식된 구간 안에서는 자르지 않는다(표 맨 위에서 자르는 것은 된다)
    boxes = [[w["x"], w["y"], w["x"] + w["w"], w["y"] + w["h"], w["text"]] for w in words]
    zones = table_zones(boxes, np.asarray(img.convert("L")), img.width)
    in_table = lambda ln: any(z0 + 5 < ln["y0"] and ln["y0"] < z1 for z0, z1 in zones)
    cuts = [(0, "시작")]
    rows, row_bottom = 0, -1  # 현재 단락의 줄 수(같은 높이에 나란한 상자는 한 줄로 센다)
    for i, ln in enumerate(lines):
        if is_header(ln, median_h) and rows >= 2 and not in_table(ln):
            prev_bottom = max((l["y1"] for l in lines[:i] if l["y1"] <= ln["y0"] + 2), default=cuts[-1][0])
            lo = max(prev_bottom, cuts[-1][0] + min_h)
            y, kind = best_cut(lo, ln["y0"], std, covered, ln["y0"])
            if y is not None and y - cuts[-1][0] >= min_h:
                cuts.append((y, kind))
                rows, row_bottom = 0, -1
        if ln["y0"] >= cuts[-1][0] and ln["y0"] > row_bottom:
            rows += 1
            row_bottom = ln["y1"]
    cuts.append((h, "끝"))
    secs = []
    for (a, kind), (b, _) in zip(cuts, cuts[1:]):
        text = "\n".join(l["text"] for l in lines if a <= (l["y0"] + l["y1"]) / 2 < b)
        secs.append({"y0": a, "y1": b, "cut": kind, "text": text})
    return secs


# ---------------------------------------------------------------- LLM 입력 묶음과 토큰 추정

def patches(w: int, h: int) -> int:
    """gpt-5.6 detail=high: 2048x2048 안에 맞추고 32px 칸 2,500개 이하로 줄인 뒤의 칸 수."""
    s = min(1.0, 2048 / max(w, h))
    w1, h1 = w * s, h * s
    while math.ceil(w1 / 32) * math.ceil(h1 / 32) > 2500:
        w1, h1 = w1 * 0.98, h1 * 0.98
    return math.ceil(w1 / 32) * math.ceil(h1 / 32)


def chunk_plan(secs: list[dict], width: int, std, covered) -> list[tuple[int, int]]:
    target = round(1.5 * width)
    chunks, run = [], []
    for s in secs + [None]:
        if s is not None and s["decision"] == "남기기":
            run.append(s)
            continue
        if run:  # 이웃한 남긴 단락들 [run] 을 target 안에서 나눈다
            a, end = run[0]["y0"], run[-1]["y1"]
            bounds = sorted({x["y0"] for x in run} | {end})
            while end - a > target:
                inside = [b for b in bounds if a + 0.4 * target <= b <= a + target]
                if inside:
                    y = max(inside)
                else:
                    y, _ = best_cut(int(a + 0.6 * target), int(a + target), std, covered, int(a + target))
                    y = y or int(a + target)
                chunks.append((a, y))
                a = y
            chunks.append((a, end))
            run = []
    return chunks


# ---------------------------------------------------------------- main

READERS = {"tesseract": "Tesseract", "paddle": "PaddleOCR"}


def paddle_words(stem: str) -> list[dict]:
    boxes = json.load(open(os.path.join(PF, "paddle_boxes", stem + ".json"), encoding="utf-8"))
    return [{"key": i, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "text": s}
            for i, (x1, y1, x2, y2, s) in enumerate(boxes)]


def text_in(words: list[dict], a: int, b: int) -> str:
    return "\n".join(l["text"] for l in lines_of(words) if a <= (l["y0"] + l["y1"]) / 2 < b)


def counter() -> dict:
    return {"units": 0, "drop": 0, "mixed": 0, "calls": 0, "in": 0.0, "out": 0.0, "area": 0, "area_drop": 0}


def tally(acc: dict, d: dict, y0: int, y1: int) -> None:
    acc["units"] += 1
    acc["area"] += y1 - y0
    if d["decision"] == "빼기":
        acc["drop"] += 1
        acc["area_drop"] += y1 - y0
    elif d["mixed"]:
        acc["mixed"] += 1


def main() -> None:
    for d in ("sec", "map", "tsv"):
        os.makedirs(os.path.join(PF, d), exist_ok=True)
    calls, out_tok_by_img = {}, defaultdict(int)
    for line in open(os.path.join(OUT_DIR, LLM, "_calls.jsonl"), encoding="utf-8"):
        c = json.loads(line)
        calls[(c["file"], c["tile"])] = c
        out_tok_by_img[c["file"]] += c["output_tokens"]
    imgs = images_by_posting()

    # 토큰 추정식 보정: 기존 59조각 실측 입력 토큰 = a * 칸 수 + b
    xs, ys = [], []
    for ims in imgs.values():
        for im in ims:
            with Image.open(os.path.join(IMG_DIR, im["file"])) as src:
                for k, (y0, y1) in enumerate(tiles_for(src), 1):
                    xs.append(patches(src.width, y1 - y0))
                    ys.append(calls[(im["file"], k)]["input_tokens"])
    a_fit, b_fit = np.polyfit(xs, ys, 1)
    fit_err = float(np.mean([abs(a_fit * x + b_fit - y) / y for x, y in zip(xs, ys)]))
    est_in = lambda w, h: a_fit * patches(w, h) + b_fit

    stems = [os.path.splitext(im["file"])[0] for ims in imgs.values() for im in ims]
    has_paddle = all(os.path.exists(os.path.join(PF, "paddle_boxes", s + ".json")) for s in stems)
    avail = ["tesseract"] + (["paddle"] if has_paddle else [])
    titles = {t["rec_idx"]: t for t in load_targets()}
    acc = {f"{r}:{m}": counter() for r in avail for m in ("fixed", "sec")}
    full = {"in": 0, "out": 0, "calls": 0}
    readers = {r: [] for r in avail}
    for rid, ims in imgs.items():
        posts = {r: {"rec_idx": rid, "company": titles[rid]["company"], "title": titles[rid]["title"], "images": []}
                 for r in avail}
        for im in ims:
            stem = os.path.splitext(im["file"])[0]
            img = Image.open(os.path.join(IMG_DIR, im["file"])).convert("RGB")
            W, H = img.size
            img.resize((220, max(1, round(H * 220 / W)))).save(os.path.join(PF, "map", stem + ".jpg"), quality=80)
            tiles = tiles_for(img)
            for k in range(1, len(tiles) + 1):
                c = calls[(im["file"], k)]
                full["in"] += c["input_tokens"]
                full["out"] += c["output_tokens"]
                full["calls"] += 1
            words_by = {r: tess_words(stem, img) if r == "tesseract" else paddle_words(stem) for r in avail}
            for r in avail:
                words = words_by[r]
                std, covered = row_stats(img, words)
                total_chars = max(1, sum(len(flat(w["text"])) for w in words))
                # 고정 조각(실측 토큰) — 같은 OCR 글자로 판정
                fx = acc[f"{r}:fixed"]
                for k, (y0, y1) in enumerate(tiles, 1):
                    if r == "tesseract":
                        t = open(os.path.join(PF, "tess", f"{stem}_t{k:02d}.txt"), encoding="utf-8").read()
                    else:
                        t = text_in(words, y0, y1)
                    d = decide(t)
                    tally(fx, d, y0, y1)
                    if d["decision"] == "남기기":
                        c = calls[(im["file"], k)]
                        fx["calls"] += 1
                        fx["in"] += c["input_tokens"]
                        fx["out"] += c["output_tokens"]
                # 단락
                sc = acc[f"{r}:sec"]
                secs = split_sections(img, words)
                for j, s in enumerate(secs, 1):
                    s.update(decide(s["text"]))
                    s["id"] = f"{r[0]}_{stem}_s{j:02d}"
                    crop = img.crop((0, s["y0"], W, s["y1"]))
                    view = crop if crop.width <= 900 else crop.resize((900, max(1, round(crop.height * 900 / crop.width))))
                    view.save(os.path.join(PF, "sec", s["id"] + ".jpg"), quality=85)
                    s["html"] = highlight(s["text"])
                    s["warn"] = ""
                    if s["decision"] == "빼기":  # 다른 OCR 글자로 다시 보면 남길 낱말·기술명이 있는가
                        for o in avail:
                            if o != r:
                                x = decide(text_in(words_by[o], s["y0"], s["y1"]))
                                if x["keep"] or x["tech"]:
                                    s["warn"] = f"{READERS[o]} 글자로는 " + ", ".join(x["keep"] + x["tech"])[:80]
                                    sc["warn"] = sc.get("warn", 0) + 1
                    tally(sc, s, s["y0"], s["y1"])
                chunk_list = []
                for ci, (a, b) in enumerate(chunk_plan(secs, W, std, covered), 1):
                    chars = sum(len(flat(w["text"])) for w in words if a <= w["y"] + w["h"] / 2 < b)
                    ei, eo = est_in(W, b - a), out_tok_by_img[im["file"]] * chars / total_chars
                    sc["calls"] += 1
                    sc["in"] += ei
                    sc["out"] += eo
                    chunk_list.append({"n": ci, "y0": a, "y1": b, "in": round(ei), "out": round(eo)})
                    for s in secs:
                        if s["decision"] == "남기기" and a <= s["y0"] < b:
                            s["chunk"] = ci
                keys = ("id", "y0", "y1", "cut", "decision", "reason", "keep", "drop", "tech", "chars", "mixed", "html", "warn")
                posts[r]["images"].append({"file": im["file"], "stem": stem, "w": W, "h": H, "url": im["url"],
                                           "sections": [{k: s[k] for k in keys} | {"chunk": s.get("chunk")} for s in secs],
                                           "chunks": chunk_list})
                print(f"  [{r:<9}] {im['file']:<18} 단락 {len(secs):>2}개 (빼기 {sum(s['decision'] == '빼기' for s in secs)}) · "
                      f"LLM 묶음 {len(chunk_list)}개", flush=True)
        for r in avail:
            readers[r].append(posts[r])

    loc_time = {}
    t_rows = list(csv.DictReader(open(os.path.join(OUT_DIR, "tesseract", "_timing.tsv"), encoding="utf-8"), delimiter="\t"))
    loc_time["tesseract"] = sum(float(x["seconds"]) for x in t_rows) / len(t_rows)
    tp = os.path.join(PF, "paddle_boxes", "_timing.json")
    if os.path.exists(tp):
        tj = json.load(open(tp, encoding="utf-8"))
        loc_time["paddle"] = sum(tj.values()) / len(tj)
    usd = lambda i, o: i / 1e6 * PRICE_IN + o / 1e6 * PRICE_OUT
    rows = [{"name": "빼지 않음 (기존 실측)", "units": full["calls"], "drop": 0, "area": "0%", "mixed": "-",
             "calls": full["calls"], "in": full["in"], "out": full["out"], "usd": usd(full["in"], full["out"]),
             "est": False, "loc": "-", "warn": "-"}]
    for r in avail:
        for m, label, est in (("fixed", "고정 조각에서 빼기", False), ("sec", "단락으로 나눠 빼기", True)):
            x = acc[f"{r}:{m}"]
            rows.append({"name": f"{label} · 판정 글자 {READERS[r]}", "units": x["units"], "drop": x["drop"],
                         "area": f"{x['area_drop'] / x['area'] * 100:.0f}%", "mixed": x["mixed"], "calls": x["calls"],
                         "in": x["in"], "out": x["out"], "usd": usd(x["in"], x["out"]), "est": est,
                         "loc": f"{loc_time[r]:.1f}초" if r in loc_time else "-",
                         "warn": x.get("warn", 0) if m == "sec" and len(avail) > 1 else "-"})
    summary = {"fit": f"입력 토큰 ≈ {a_fit:.3f} × 칸 수 + {b_fit:.0f} (기존 59조각 실측으로 맞춤, 평균 오차 {fit_err * 100:.1f}%)",
               "rows": rows}
    for x in rows:
        print(f"{x['name']:<34} 단위 {x['units']:>3} 빼기 {x['drop']:>3} 높이 {x['area']:>4} 섞임 {x['mixed']:>2} "
              f"호출 {x['calls']:>3} 입력 {x['in']:>9,.0f} 출력 {x['out']:>7,.0f} ${x['usd']:.4f}"
              f"{' (추정)' if x['est'] else ''} 위치찾기 {x['loc']}")
    print(summary["fit"])
    blob = {"summary": summary, "readers": readers, "names": {r: READERS[r] for r in avail}}
    with open(os.path.join(PF, "sections.json"), "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False)
    with open(os.path.join(PF, "sections.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", json.dumps(blob, ensure_ascii=False).replace("</", "<\\/")))
    print("-> out/page_filter/sections.html")


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>단락 나누기 확인</title>
<style>
:root{--bg:#f6f6f4;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--accent:#2a5bd7;
--keep:#cdeccf;--drop:#f6cfcf;--tech:#cfe0ff;--okc:#3b9b4a;--dropc:#d24b4b;--ambc:#9a9993;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--panel:#1f1f1d;--ink:#e9e8e3;--muted:#9a9993;--line:#34332f;--accent:#7ea2ff;
--keep:#24502a;--drop:#5c2626;--tech:#22385f;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Segoe UI","Malgun Gothic",sans-serif}
header{position:sticky;top:0;z-index:3;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center}
header h1{font-size:16px;margin:0}.small{color:var(--muted);font-size:12px}
.layout{display:flex}nav{width:230px;flex:none;border-right:1px solid var(--line);padding:8px;position:sticky;top:50px;height:calc(100vh - 50px);overflow:auto}
nav button{display:block;width:100%;text-align:left;background:none;border:0;border-radius:6px;padding:6px 8px;color:inherit;font:inherit;cursor:pointer}
nav button.on{background:var(--panel);box-shadow:inset 3px 0 0 var(--accent)}nav small{display:block;color:var(--muted);font-size:12px}
main{flex:1;min-width:0;padding:12px 16px}h2{font-size:17px;margin:0 0 4px}h3{font-size:14px;margin:18px 0 8px}
table.cmp{border-collapse:collapse;font-size:13px;margin:6px 0 4px;background:var(--panel)}table.cmp th,table.cmp td{border:1px solid var(--line);padding:5px 9px;text-align:right}
table.cmp th:first-child,table.cmp td:first-child{text-align:left}.wrap{overflow-x:auto}
.imgblock{display:flex;gap:12px;align-items:flex-start}
.map{position:sticky;top:62px;flex:none;width:236px;max-height:calc(100vh - 80px);overflow:auto;border:1px solid var(--line);border-radius:6px;background:var(--panel);padding:8px}
.mapin{position:relative;width:220px}.mapin img{width:220px;display:block}
.ov{position:absolute;left:0;width:220px;border-top:2px solid #000a;cursor:pointer}
.ov.빼기{background:rgba(210,75,75,.38)}.ov.남기기{background:rgba(59,155,74,.12)}.ov.amb{background:rgba(150,150,150,.25)}
.ch{position:absolute;right:-2px;width:8px;background:var(--accent);opacity:.75;border-radius:2px}
.cards{flex:1;min-width:0}
.card{display:grid;grid-template-columns:minmax(220px,1.1fr) 230px minmax(220px,1fr);gap:10px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px;margin-bottom:10px;border-left:5px solid var(--okc)}
.card.빼기{border-left-color:var(--dropc)}.card.amb{border-left-color:var(--ambc)}
.imgbox,.txt{max-height:440px;overflow:auto;border:1px solid var(--line);border-radius:6px}.imgbox img{width:100%;display:block}
.txt pre{margin:0;padding:8px;white-space:pre-wrap;word-break:break-word;font:12px/1.5 ui-monospace,Consolas,"Malgun Gothic",monospace}
.colh{font-size:12px;color:var(--muted);margin-bottom:4px}.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-weight:600;color:#fff;background:var(--okc)}
.badge.빼기{background:var(--dropc)}.warn{color:#c27400;font-weight:600}.info p{margin:5px 0;font-size:12.5px}.verdict label{display:block;font-size:13px;margin:2px 0}
.verdict input[type=text]{width:100%;margin-top:4px;padding:4px 6px;border:1px solid var(--line);border-radius:5px;background:var(--panel);color:inherit}
mark.keep{background:var(--keep);color:inherit}mark.drop{background:var(--drop);color:inherit}mark.tech{background:var(--tech);color:inherit}
textarea{width:100%;height:140px;font:12px ui-monospace,Consolas,monospace;background:var(--panel);color:inherit;border:1px solid var(--line);border-radius:6px;padding:6px}
@media (max-width:1150px){.card{grid-template-columns:1fr 1fr}}@media (max-width:800px){.layout,.imgblock{display:block}nav{position:static;width:auto;height:auto}.map{position:static;width:auto}.card{grid-template-columns:1fr}}
</style></head><body>
<header><h1>단락 나누기 확인</h1><span class="small">왼쪽 지도: 빨강=빼기, 초록=남기기, 회색=애매 · 파란 막대=LLM 입력 묶음 · 지도에서 단락을 누르면 그 카드로 이동</span>
<label class="small">위치 찾기 <select id="reader"></select></label>
<label class="small"><input type="checkbox" id="onlyDrop"> 빼기만 보기</label></header>
<div class="layout"><nav id="nav"></nav><main id="main"></main></div>
<script>
const D = __DATA__;
let R = D.readers.paddle ? "paddle" : "tesseract", P = D.readers[R];
const KEY = "section_verdicts_v1";
let V = {}; try { V = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
let cur = -1;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = n => Math.round(n).toLocaleString();
function save(){ try { localStorage.setItem(KEY, JSON.stringify(V)); } catch (e) {} summary(); }
function nav(){
  $("nav").innerHTML = "";
  const b0 = document.createElement("button"); b0.className = cur === -1 ? "on" : ""; b0.innerHTML = "전체 비교<small>고정 조각 vs 단락</small>";
  b0.onclick = () => { cur = -1; render(); }; $("nav").appendChild(b0);
  P.forEach((p, i) => {
    const all = p.images.flatMap(im => im.sections), d = all.filter(s => s.decision === "빼기").length;
    const chk = all.filter(s => V[s.id] && V[s.id].v).length;
    const b = document.createElement("button"); b.className = i === cur ? "on" : "";
    b.innerHTML = esc(p.company) + "<small>단락 " + all.length + " · 빼기 " + d + " · 확인 " + chk + "/" + all.length + "</small>";
    b.onclick = () => { cur = i; render(); window.scrollTo(0, 0); }; $("nav").appendChild(b);
  });
}
function overview(){
  const rows = D.summary.rows;
  let h = "<h2>전체 비교 (10건, 이미지 14장)</h2><div class='wrap'><table class='cmp'><tr><th>방식</th><th>판정 단위</th><th>뺀 단위</th><th>뺀 높이</th><th>섞인 단위(남김)</th><th>LLM 호출</th><th>입력 토큰</th><th>출력 토큰</th><th>LLM 비용</th><th>위치 찾기 시간(이미지당)</th><th>뺀 단락 중 다른 OCR 경고</th></tr>";
  rows.forEach(r => h += "<tr><td>" + esc(r.name) + "</td><td>" + r.units + "</td><td>" + r.drop + "</td><td>" + r.area + "</td><td>" + r.mixed +
    "</td><td>" + r.calls + "</td><td>" + fmt(r.in) + "</td><td>" + fmt(r.out) + "</td><td>$" + r.usd.toFixed(4) + (r.est ? " (추정)" : "") + "</td><td>" + esc(r.loc) + "</td><td>" + esc(r.warn) + "</td></tr>");
  h += "</table></div><p class='small'>섞인 단위 = 남길 낱말과 뺄 낱말이 함께 있어 통째로 남은 단위. '단락' 행의 토큰은 추정: " + esc(D.summary.fit) +
       ", 출력 토큰은 이미지별 기존 실측 출력을 그 구간의 OCR 글자 수 비율로 나눔. 실제 값은 LLM을 다시 돌려야 확정된다. " +
       "위치 찾기 시간은 그 OCR로 이미지 전체를 읽는 CPU 시간이다(빼기 판정을 하려면 먼저 한 번 읽어야 한다).</p>" +
       "<p>왼쪽에서 공고를 골라 단락이 제대로 나뉘었는지, 판정이 맞는지 확인해 주세요. 맨 아래 칸에 틀렸다고 표시한 단락이 모입니다.</p>";
  return h;
}
function words(l, xs){ return xs.length ? "<p><b>" + l + "</b> " + xs.map(esc).join(", ") + "</p>" : ""; }
function render(){
  nav();
  let h;
  if (cur === -1) h = overview();
  else {
    const p = P[cur], only = $("onlyDrop").checked;
    h = "<h2>" + esc(p.company) + " — " + esc(p.title) + "</h2><div class='small'>rec_idx " + esc(p.rec_idx) +
        " · <a href='https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=" + esc(p.rec_idx) + "' target='_blank' rel='noopener'>사람인 공고 ↗</a></div>";
    p.images.forEach(im => {
      h += "<h3>" + esc(im.file) + " <span class='small'>(" + im.w + "x" + im.h + ", 단락 " + im.sections.length + "개, LLM 묶음 " + im.chunks.length +
           "개: " + im.chunks.map(c => "#" + c.n + " " + (c.y1 - c.y0) + "px").join(", ") + ") · <a href='" + esc(im.url) + "' target='_blank' rel='noopener'>원본 주소 ↗</a></span></h3>";
      h += "<div class='imgblock'><div class='map'><div class='mapin'><img src='map/" + esc(im.stem) + ".jpg' alt=''>";
      im.sections.forEach(s => { const amb = s.reason.startsWith("애매") ? " amb" : "";
        h += "<div class='ov " + s.decision + amb + "' data-go='" + s.id + "' title='" + esc(s.id + " " + s.decision) + "' style='top:" + (s.y0 / im.h * 100) + "%;height:" + ((s.y1 - s.y0) / im.h * 100) + "%'></div>"; });
      im.chunks.forEach(c => h += "<div class='ch' title='LLM 묶음 #" + c.n + "' style='top:" + (c.y0 / im.h * 100) + "%;height:" + ((c.y1 - c.y0) / im.h * 100) + "%'></div>");
      h += "</div></div><div class='cards'>";
      im.sections.forEach((s, i) => {
        if (only && s.decision !== "빼기") return;
        const amb = s.reason.startsWith("애매") ? " amb" : "", v = V[s.id] || {};
        h += "<section class='card " + s.decision + amb + "' id='" + s.id + "' data-id='" + s.id + "'>" +
          "<div><div class='colh'>단락 " + (i + 1) + "/" + im.sections.length + " · y " + s.y0 + "–" + s.y1 + " (" + (s.y1 - s.y0) + "px) · 위쪽 자른 곳: " + esc(s.cut) + "</div>" +
          "<div class='imgbox'><img loading='lazy' src='sec/" + s.id + ".jpg' alt=''></div></div>" +
          "<div class='info'><span class='badge " + s.decision + "'>" + s.decision + "</span>" + (s.chunk ? " <span class='small'>→ LLM 묶음 #" + s.chunk + "</span>" : "") +
          "<p>" + esc(s.reason) + " · 글자 " + s.chars + "자</p>" + (s.warn ? "<p class='warn'>⚠ " + esc(s.warn) + "</p>" : "") + words("남길 낱말:", s.keep) + words("뺄 낱말:", s.drop) + words("기술명:", s.tech) +
          "<div class='verdict'><div class='colh'>내 확인</div>" +
          ["맞음", "틀림-남겨야 함", "틀림-빼도 됨", "나누기가 이상함"].map(o => "<label><input type='radio' name='v_" + s.id + "' value='" + o + "'" + (v.v === o ? " checked" : "") + "> " + o + "</label>").join("") +
          "<input type='text' placeholder='메모(선택)' value='" + esc(v.note || "") + "'></div></div>" +
          "<div><div class='colh'>판정에 쓴 글자 (" + esc(D.names[R]) + ")</div><div class='txt'><pre>" + (s.html || "(글자 없음)") + "</pre></div></div></section>";
      });
      h += "</div></div>";
    });
  }
  h += "<h3>내 확인 결과 (틀렸다고 표시한 단락) — 이 칸을 복사해 Claude에게 붙여 주세요</h3><textarea id='out' readonly></textarea>" +
       "<div class='small'>표시는 이 브라우저에 저장됩니다.</div>";
  $("main").innerHTML = h;
  document.querySelectorAll(".ov").forEach(o => o.onclick = () => { const t = document.getElementById(o.dataset.go); if (t) t.scrollIntoView({behavior: "smooth", block: "start"}); });
  document.querySelectorAll(".card").forEach(sec => {
    const id = sec.dataset.id;
    sec.querySelectorAll("input[type=radio]").forEach(r => r.onchange = () => { V[id] = Object.assign(V[id] || {}, {v: r.value}); save(); nav(); });
    sec.querySelector("input[type=text]").oninput = e => { V[id] = Object.assign(V[id] || {}, {note: e.target.value}); save(); };
  });
  summary();
}
function summary(){
  const el = $("out"); if (!el) return;
  const lines = ["단락\t판정\t내 확인\t메모"]; let n = 0, wrong = 0, total = 0;
  P.forEach(p => p.images.forEach(im => im.sections.forEach(s => { total++; const v = V[s.id]; if (!v || !v.v) return; n++;
    if (v.v !== "맞음" || v.note) { if (v.v !== "맞음") wrong++; lines.push([s.id, s.decision, v.v, v.note || ""].join("\t")); } })));
  el.value = "확인한 단락 " + n + "/" + total + ", 틀림 " + wrong + "\n" + lines.join("\n");
}
Object.entries(D.names).forEach(([k, n]) => { const o = document.createElement("option"); o.value = k; o.textContent = n; o.selected = k === R; $("reader").appendChild(o); });
$("reader").onchange = e => { R = e.target.value; P = D.readers[R]; render(); };
$("onlyDrop").onchange = render;
if (/^#\d+$/.test(location.hash)) cur = Math.min(P.length - 1, parseInt(location.hash.slice(1), 10));
render();
</script></body></html>
"""

def main_paddle_only() -> None:
    """새 샘플용: PaddleOCR 줄 상자만으로 단락을 나누고 판정한다(Tesseract·기존 LLM 조각 비교 없음).
    결과 형식은 main() 과 같아서 extract_skills.py 가 그대로 읽는다."""
    for d in ("sec", "map"):
        os.makedirs(os.path.join(PF, d), exist_ok=True)
    titles = {t["rec_idx"]: t for t in load_targets()}
    posts, n_sec, n_drop = [], 0, 0
    for rid, ims in images_by_posting().items():
        post = {"rec_idx": rid, "company": titles[rid]["company"], "title": titles[rid]["title"], "images": []}
        for im in ims:
            stem = os.path.splitext(im["file"])[0]
            img = Image.open(os.path.join(IMG_DIR, im["file"])).convert("RGB")
            W, H = img.size
            img.resize((220, max(1, round(H * 220 / W)))).save(os.path.join(PF, "map", stem + ".jpg"), quality=80)
            words = paddle_words(stem)
            std, covered = row_stats(img, words)
            secs = split_sections(img, words)
            for j, s in enumerate(secs, 1):
                s.update(decide(s["text"]))
                s["id"] = f"p_{stem}_s{j:02d}"
                crop = img.crop((0, s["y0"], W, s["y1"]))
                view = crop if crop.width <= 900 else crop.resize((900, max(1, round(crop.height * 900 / crop.width))))
                view.save(os.path.join(PF, "sec", s["id"] + ".jpg"), quality=85)
                s["html"], s["warn"] = highlight(s["text"]), ""
            chunks = [{"n": i, "y0": a, "y1": b, "in": 0, "out": 0}
                      for i, (a, b) in enumerate(chunk_plan(secs, W, std, covered), 1)]
            for c in chunks:
                for s in secs:
                    if s["decision"] == "남기기" and c["y0"] <= s["y0"] < c["y1"]:
                        s["chunk"] = c["n"]
            keys = ("id", "y0", "y1", "cut", "decision", "reason", "keep", "drop", "tech", "chars", "mixed", "html", "warn")
            post["images"].append({"file": im["file"], "stem": stem, "w": W, "h": H, "url": im["url"],
                                   "sections": [{k: s[k] for k in keys} | {"chunk": s.get("chunk")} for s in secs],
                                   "chunks": chunks})
            n_sec += len(secs)
            n_drop += sum(s["decision"] == "빼기" for s in secs)
            print(f"  {im['file']:<18} 단락 {len(secs):>2}개 (빼기 {sum(s['decision'] == '빼기' for s in secs)})", flush=True)
        posts.append(post)
    summary = {"fit": "-", "rows": [{"name": "단락으로 나눠 빼기 · 판정 글자 PaddleOCR", "units": n_sec, "drop": n_drop,
                                     "area": "-", "mixed": "-", "calls": 0, "in": 0, "out": 0, "usd": 0, "est": True,
                                     "loc": "-", "warn": "-"}]}
    blob = {"summary": summary, "readers": {"paddle": posts}, "names": {"paddle": "PaddleOCR"}}
    with open(os.path.join(PF, "sections.json"), "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False)
    with open(os.path.join(PF, "sections.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", json.dumps(blob, ensure_ascii=False).replace("</", "<\\/")))
    print(f"단락 {n_sec}개 중 빼기 {n_drop}개 -> {os.path.relpath(PF)}/sections.html")


if __name__ == "__main__":
    if "--paddle-only" in sys.argv:
        main_paddle_only()
    else:
        main()
