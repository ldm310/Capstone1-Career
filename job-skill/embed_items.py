"""
필수·우대 줄 임베딩: DB 의 현재 추출 결과(백엔드·데이터 엔지니어 자리)에서 필수·우대 한 줄씩 꺼내 OpenAI 임베딩으로 바꾼다.
비슷한 줄끼리 묶어 카테고리를 정하기 위한 첫 단계다.

  다듬기: 연차("3년 이상", "2~5년")와 끝에 붙은 정도 말("경험", "능력", "이해", "보유" …)을 뺀다.
          "Java 3년 이상 경험"과 "Python 3년 이상 경험"이 말투가 같아 묶이지 않게 — 연차·정도는 레벨 정할 때 따로 쓴다.
          다듬은 글이 같으면 한 번만 임베딩한다.
  다시 돌리면: 지난번에 임베딩한 글은 그대로 쓰고 새 글만 부른다(돈 아끼기).
  결과: out/embed/<모델>/
          vectors.npy  임베딩 (글 수 × 차원, float32, 길이 1로 맞춰져 있음)
          texts.tsv    row(vectors.npy 의 줄 번호) · 임베딩한 글 · 줄 수 · 필수 수 · 우대 수
          items.tsv    item_id · posting_id · 칸 · 원래 글 · row · 자리 직무
          meta.json    모델 · 개수 · 토큰 · 비용

실행: py -3.12 embed_items.py [--model text-embedding-3-large]
      py -3.12 embed_items.py --jobs-from out/fill_unit_job/gpt-5.6-luna/decisions.jsonl   # RDS 에 직무 칸이 아직 없을 때
환경변수 OPENAI_API_KEY 필요. DB 는 db_load.connect() 와 같음(RDS 설정이 있으면 RDS).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone

import numpy as np

import db_load

HERE = os.path.dirname(os.path.abspath(__file__))
PRICES = {"text-embedding-3-large": 0.13, "text-embedding-3-small": 0.02}  # USD/1M 토큰
BATCH = 1000

ITEMS_SQL = """
SELECT ui.id, er.posting_id, ui.category, ui.text, ru.job
FROM unit_item ui
JOIN recruit_unit ru ON ru.id = ui.unit_id
JOIN extraction_run er ON er.id = ru.run_id
WHERE er.is_current AND ru.job IN ('백엔드', '데이터 엔지니어') AND ui.category IN ('필수', '우대')
ORDER BY ui.id
"""
# RDS 에 직무 칸이 아직 없을 때: IT 자리의 줄을 꺼내고, fill_unit_job.py --dry-run 이 남긴 직무 판단으로 거른다(--jobs-from).
ITEMS_SQL_IT = """
SELECT ui.id, er.posting_id, ui.category, ui.text, ru.id
FROM unit_item ui
JOIN recruit_unit ru ON ru.id = ui.unit_id
JOIN extraction_run er ON er.id = ru.run_id
WHERE er.is_current AND ru.is_it AND ui.category IN ('필수', '우대')
ORDER BY ui.id
"""


def load_items(jobs_from: str | None) -> list[tuple]:
    """(item_id, posting_id, 칸, 글, 직무). jobs_from 이 있으면 그 파일의 최신 지시문 판단 중 백엔드·데이터 엔지니어 자리만."""
    with db_load.connect() as conn:
        if not jobs_from:
            return conn.execute(ITEMS_SQL).fetchall()
        rows = conn.execute(ITEMS_SQL_IT).fetchall()
    from extract_skills import TARGET_JOBS
    from fill_unit_job import PROMPT_VERSION
    jobs = {}
    for ln in open(jobs_from, encoding="utf-8"):
        r = json.loads(ln)
        if r["prompt"] == PROMPT_VERSION:
            jobs[r["unit_id"]] = r["job"]
    if not jobs:
        sys.exit(f"{jobs_from} 에 지금 지시문({PROMPT_VERSION})의 직무 판단이 없습니다. fill_unit_job.py --dry-run 을 먼저 돌리세요.")
    kept = [(*r[:4], jobs[r[4]]) for r in rows if jobs.get(r[4]) in TARGET_JOBS]
    print(f"직무 판단 파일로 거름: IT 자리 줄 {len(rows)}개 → 백엔드·데이터 엔지니어 자리 줄 {len(kept)}개"
          f" (판단 없는 자리 {len({r[4] for r in rows if r[4] not in jobs})}개는 뺌)")
    return kept

NUM = r"\d+(?:\.\d+)?"
# 연차: "3년 이상", "2~5년", "1년 6개월", "최소 3년". "(4년)"·"(2,3년)"·"4년제"는 학력 표시라 남긴다.
YEARS = re.compile(
    rf"(?<![\(\d,])(?:최소\s*)?{NUM}\s*(?:[~∼\-]\s*{NUM}\s*)?(?:년|개월)(?!\s*제)"
    rf"(?:\s*{NUM}\s*개월)?(?:\s*(?:이상|이하|미만|초과|차|정도|내외))?"
)
# 끝에 붙은 정도 말. 뒤에서부터 하나씩 뺀다(남는 글이 있을 때만).
TAIL_WORDS = (
    "유경험", "경험", "경력", "실무", "능력", "역량", "가능자", "가능", "보유자", "보유", "이해도", "이해", "지식",
    "능숙", "능통", "숙련", "익숙함", "우수", "소지자", "소지", "활용", "사용", "우대", "필수", "이상", "이하",
    "기본", "기초", "있는 분", "있으신 분", "분", "자",
    # "SQL에 대한 높은 이해도"처럼 정도를 꾸미는 말 — 남으면 "~에 대한 높은"끼리 묶인다
    "기본적인", "가능한", "높은", "깊은", "깊이 있는", "탄탄한", "충분한", "능숙한", "익숙한", "뛰어난", "우수한",
    "폭넓은", "해박한", "풍부한",
)
TAIL = re.compile(r"\s*(?:" + "|".join(re.escape(w) for w in sorted(TAIL_WORDS, key=len, reverse=True)) + r")\s*$")
DANGLING = re.compile(r"(?:\s*(?:[~∼\-·,/]|및|또는|(?:이|그)에\s*준하는|에\s*대한|에\s*대해|에\s*관한|대한|관련)\s*)+$")
PARTICLE = re.compile(r"(?<=[가-힣A-Za-z0-9)])(?:에|을|를)$")   # "커뮤니케이션에 (능숙한)" → "커뮤니케이션"


def clean(text: str) -> str:
    """임베딩할 글: 연차·끝의 정도 말을 뺀 것. 다 빠지면 원래 글."""
    s = YEARS.sub(" ", text)
    s = re.sub(r"\s+", " ", s).strip()
    while True:
        s2 = PARTICLE.sub("", DANGLING.sub("", TAIL.sub("", s)).strip()).strip()
        if s2 == s or not s2:
            break
        s = s2
    s = re.sub(r"^[~∼\-·,/\s]+", "", s)
    return s or text.strip()


def load_cache(d: str) -> dict[str, np.ndarray]:
    """지난번 결과: 글 → 벡터."""
    vp, tp = os.path.join(d, "vectors.npy"), os.path.join(d, "texts.tsv")
    if not (os.path.exists(vp) and os.path.exists(tp)):
        return {}
    vecs = np.load(vp)
    with open(tp, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return {r["text"]: vecs[int(r["row"])] for r in rows}


def embed(client, model: str, texts: list[str]) -> tuple[np.ndarray, int]:
    out, tokens = [], 0
    for i in range(0, len(texts), BATCH):
        part = texts[i:i + BATCH]
        r = client.embeddings.create(model=model, input=part)
        out.extend(d.embedding for d in sorted(r.data, key=lambda d: d.index))
        tokens += r.usage.total_tokens
        print(f"  {min(i + BATCH, len(texts))}/{len(texts)}  토큰 {tokens}", flush=True)
    return np.asarray(out, dtype=np.float32), tokens


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="text-embedding-3-large")
    ap.add_argument("--jobs-from", help="RDS 에 직무 칸이 없을 때 쓸 직무 판단 파일(out/fill_unit_job/<모델>/decisions.jsonl)")
    args = ap.parse_args()

    items = load_items(args.jobs_from)
    print(f"필수·우대 줄 {len(items)}개")

    rows: dict[str, int] = {}          # 다듬은 글 → row
    counts: list[dict] = []
    item_rows = []
    for item_id, posting_id, cat, text, job in items:
        e = clean(text)
        if e not in rows:
            rows[e] = len(rows)
            counts.append({"n": 0, "필수": 0, "우대": 0})
        r = rows[e]
        counts[r]["n"] += 1
        counts[r][cat] += 1
        item_rows.append((item_id, posting_id, cat, text, r, job))
    texts = list(rows)
    print(f"다듬은 뒤 서로 다른 글 {len(texts)}개")

    d = os.path.join(HERE, "out", "embed", args.model)
    os.makedirs(d, exist_ok=True)
    cache = load_cache(d)
    new = [t for t in texts if t not in cache]
    print(f"지난번 것 그대로 {len(texts) - len(new)}개, 새로 부를 글 {len(new)}개")

    tokens = 0
    if new:
        from openai import OpenAI
        vecs, tokens = embed(OpenAI(max_retries=4, timeout=120), args.model, new)
        cache.update(zip(new, vecs))
    usd = tokens / 1e6 * PRICES.get(args.model, 0)

    mat = np.stack([cache[t] for t in texts])
    np.save(os.path.join(d, "vectors.npy"), mat)
    with open(os.path.join(d, "texts.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["row", "text", "n", "필수", "우대"])
        for t, r in rows.items():
            w.writerow([r, t, counts[r]["n"], counts[r]["필수"], counts[r]["우대"]])
    with open(os.path.join(d, "items.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["item_id", "posting_id", "category", "text", "row", "job"])
        w.writerows(item_rows)
    meta = {"model": args.model, "dims": int(mat.shape[1]), "items": len(items), "texts": len(texts),
            "new_texts": len(new), "tokens": tokens, "usd": round(usd, 4),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"저장: {d}  ({mat.shape[0]} × {mat.shape[1]})  토큰 {tokens}  약 ${usd:.4f}")


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
