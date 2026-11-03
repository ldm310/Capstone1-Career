"""
2단계 후보 B: 이미지를 읽는 LLM 이 이미지를 글자로 옮긴다 (OpenAI Responses API).

  - 지시문: "이미지의 글자를 빠짐없이 그대로 옮겨 적어라. 요약하거나 고치지 마라." + 출력 형식 한 줄.
    조각이면 몇 번째 조각인지와 '가장자리에서 잘린 줄은 옮기지 마라(이웃 조각에 온전히 있다)'를 덧붙인다.
  - 자르기: 세로가 가로의 2배를 넘는 이미지는 높이 1.5W, 겹침 0.15W(최소 100px)로 잘라 조각마다 1회 호출.
    겹친 구간에서 두 조각에 모두 나온 줄은 앞뒤 조각 끝·처음 줄을 맞대어(줄 유사도) 한 번만 남긴다.
    조각별 원문은 out/<후보>/_tiles/ 에 그대로 남긴다.
  - detail="high", reasoning effort 는 --effort (기본 none: 옮겨 적기에는 추론이 필요 없다).
  - 기록: 호출별 입력·출력(추론 포함) 토큰과 응답 시간(API 왕복만) -> out/<후보>/_calls.jsonl (호출 즉시 추가)
    -> 끝나면 _calls.tsv, 이미지별 _timing.tsv. 중간에 끊기면 다시 실행해 장부에 있는 조각은 건너뛴다.

실행: py -3.12 run_llm.py --model gpt-5.6-terra [--effort none] [--only 54932925]
환경변수 OPENAI_API_KEY 필요.
"""

from __future__ import annotations

import argparse
import base64
import csv
import difflib
import io
import json
import os
import re
import sys
import time

from PIL import Image

from common import IMG_DIR, OUT_DIR, images_by_posting, tile_spans, write_text

BASE_PROMPT = ("이미지의 글자를 빠짐없이 그대로 옮겨 적어라. 요약하거나 고치지 마라.\n"
               "설명이나 머리말 없이 옮긴 글자만 출력하라.")
TALL_RATIO = 2.0      # 세로/가로 > 2 이면 자른다
TILE_RATIO = 1.5      # 조각 높이 = 1.5 * 가로
OVERLAP_RATIO = 0.15  # 겹침 = 0.15 * 가로
MIN_OVERLAP = 100

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def tiles_for(img: Image.Image) -> list[tuple[int, int]]:
    w, h = img.size
    if h <= TALL_RATIO * w:
        return [(0, h)]
    return tile_spans(h, round(TILE_RATIO * w), max(MIN_OVERLAP, round(OVERLAP_RATIO * w)))


def tile_prompt(k: int, n: int) -> str:
    if n == 1:
        return BASE_PROMPT
    head = f"\n이 이미지는 세로로 긴 이미지를 위에서부터 겹치게 자른 {n}조각 중 {k}번째다. "
    if k == 1:
        edge = "아래 가장자리에 걸려 글자가 일부만 보이는 줄은 옮기지 마라(다음 조각에 온전히 들어 있다)."
    elif k == n:
        edge = "위 가장자리에 걸려 글자가 일부만 보이는 줄은 옮기지 마라(앞 조각에 온전히 들어 있다)."
    else:
        edge = "위·아래 가장자리에 걸려 글자가 일부만 보이는 줄은 옮기지 마라(이웃 조각에 온전히 들어 있다)."
    return BASE_PROMPT + head + edge


def data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def merge_tiles(texts: list[str]) -> tuple[str, list[int]]:
    """앞 조각의 끝 k줄과 다음 조각의 처음 k줄이 줄마다 비슷하면(평균 유사도>=0.85, 최소>=0.6)
    가장 큰 k 만큼 다음 조각 앞부분을 뺀다. 맞는 k 가 없으면 그대로 잇는다(중복이 남을 뿐 내용은 잃지 않는다)."""
    lines = [l for l in texts[0].splitlines() if l.strip()]
    dropped = []
    for t in texts[1:]:
        nxt = [l for l in t.splitlines() if l.strip()]
        best = 0
        for k in range(1, min(len(lines), len(nxt), 40) + 1):
            a, b = lines[-k:], nxt[:k]
            sims = [difflib.SequenceMatcher(None, _norm(x), _norm(y)).ratio() for x, y in zip(a, b)]
            if min(sims) >= 0.6 and sum(sims) / k >= 0.85 and sum(len(_norm(y)) for y in b) >= 4:
                best = k
        dropped.append(best)
        lines += nxt[best:]
    return "\n".join(lines), dropped


def call_with_retry(client, req: dict, attempts: int = 8):
    """SDK 자체 재시도(4회)로도 안 되는 연결 끊김(DNS 실패 등)은 더 길게 기다렸다 다시 시도한다."""
    import openai
    for i in range(attempts):
        try:
            t = time.perf_counter()
            resp = client.responses.create(**req)
            return resp, time.perf_counter() - t
        except (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError,
                openai.InternalServerError) as e:
            wait = min(120, 10 * 2 ** i)
            print(f"    [재시도 {i + 1}/{attempts}] {type(e).__name__}: {e} -> {wait}s 대기", flush=True)
            time.sleep(wait)
    raise RuntimeError("API 호출이 계속 실패했다")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.6-terra")
    ap.add_argument("--effort", default="none", help="reasoning effort (none/low/...) — 'omit' 이면 보내지 않음")
    ap.add_argument("--only", help="이 rec_idx 만 (쉼표 구분)")
    args = ap.parse_args()

    from openai import OpenAI
    client = OpenAI(max_retries=4, timeout=300)
    cand = f"llm_{args.model}"
    tile_dir = os.path.join(OUT_DIR, cand, "_tiles")
    os.makedirs(tile_dir, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None

    ledger_path = os.path.join(OUT_DIR, cand, "_calls.jsonl")
    done = {}
    if os.path.exists(ledger_path):
        with open(ledger_path, encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                done[(c["file"], c["tile"])] = c

    calls, timing = [], []
    for rid, imgs in images_by_posting().items():
        if only and rid not in only:
            continue
        parts = []
        for im in imgs:
            with Image.open(os.path.join(IMG_DIR, im["file"])) as src:
                img = src.convert("RGB")
            spans = tiles_for(img)
            texts, t_img = [], 0.0
            for k, (y0, y1) in enumerate(spans, 1):
                tile_path = os.path.join(tile_dir, f"{os.path.splitext(im['file'])[0]}_t{k:02d}.txt")
                if (im["file"], k) in done and os.path.exists(tile_path):
                    c = done[(im["file"], k)]
                    with open(tile_path, encoding="utf-8") as f:
                        texts.append(f.read())
                    calls.append(c)
                    t_img += float(c["seconds"])
                    continue
                tile = img.crop((0, y0, img.width, y1))
                req = dict(model=args.model, max_output_tokens=16000,
                           input=[{"role": "user", "content": [
                               {"type": "input_text", "text": tile_prompt(k, len(spans))},
                               {"type": "input_image", "image_url": data_url(tile), "detail": "high"}]}])
                if args.effort != "omit":
                    req["reasoning"] = {"effort": args.effort}
                resp, sec = call_with_retry(client, req)
                t_img += sec
                text = resp.output_text or ""
                u = resp.usage
                rtok = getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", 0) or 0
                c = {"rec_idx": rid, "file": im["file"], "tile": k, "tiles": len(spans),
                     "y0": y0, "y1": y1, "width": img.width, "seconds": f"{sec:.2f}",
                     "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                     "reasoning_tokens": rtok, "status": resp.status,
                     "incomplete": getattr(getattr(resp, "incomplete_details", None), "reason", "") or ""}
                with open(tile_path, "w", encoding="utf-8") as f:
                    f.write(text)
                with open(ledger_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
                calls.append(c)
                texts.append(text)
                print(f"  {im['file']:<20} t{k}/{len(spans)} y={y0}-{y1}  {sec:5.1f}s  "
                      f"in {u.input_tokens} out {u.output_tokens} (reason {rtok})  {resp.status}", flush=True)
            merged, dropped = merge_tiles(texts) if len(texts) > 1 else (texts[0].strip(), [])
            if dropped:
                print(f"    겹침 중복 제거(줄): {dropped}")
            parts.append(merged)
            timing.append({"rec_idx": rid, "seq": im["seq"], "file": im["file"], "width": im["width"],
                           "height": im["height"], "tiles": len(spans), "seconds": f"{t_img:.2f}",
                           "dedup_lines": ",".join(map(str, dropped))})
        write_text(cand, rid, "\n\n".join(parts) + "\n")

    suffix = "" if not only else "_partial"
    for name, rows in (("_calls", calls), ("_timing", timing)):
        with open(os.path.join(OUT_DIR, cand, f"{name}{suffix}.tsv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
            w.writeheader()
            w.writerows(rows)
    tin = sum(c["input_tokens"] for c in calls)
    tout = sum(c["output_tokens"] for c in calls)
    total = sum(float(t["seconds"]) for t in timing)
    print(f"호출 {len(calls)}회, 입력 {tin} / 출력 {tout} 토큰, 이미지 {len(timing)}장 평균 {total / len(timing):.1f}s/장")


if __name__ == "__main__":
    main()
