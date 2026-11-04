"""
검증용 무작위 샘플: 사람인 직무 분류(백엔드/서버개발, 데이터엔지니어) 목록에서 0~3년차가 지원할 수 있는 공고만 골라 무작위로 뽑는다.

  - 후보: 직무 분류 목록(cat_kewd) 최신 등록순 PAGES쪽 x 100건. 목록의 경력 조건으로 최소 요구 경력 3년 이하만 남긴다
    (신입·경력무관·'경력(년수무관)'·'경력 N년↑'(N<=3)·'N ~ M년'(N<=3)).
  - 이전 샘플(targets.tsv, sample2/targets.tsv)의 공고·회사는 뺀다. 회사당 1건, 두 직무에 함께 뽑히지 않게 한다.
  - 무작위: 씨앗값 SEED 로 섞은 뒤 앞에서부터 직무별 N건. 같은 씨앗이면 같은 결과.
  - 뽑힌 공고는 본문(relay view-detail)을 열어 글 공고 / 이미지 공고 / 섞인 공고로 나눈다.
  - 요청 간격 1.2초, User-Agent 는 프로젝트 이름(fetch_images.get).
  - 결과: <출력>/targets.tsv (rec_idx, company, title, role, career, kind), <출력>/sampling_log.tsv(후보 전부), <출력>/pages/

실행: py -3.12 sample_random.py --out sample3 --per-role 10
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import random
import re
import sys

from fetch_images import RELAY, get
from sample_postings import body_stats

HERE = os.path.dirname(os.path.abspath(__file__))
LIST = ("https://www.saramin.co.kr/zf_user/jobs/list/job-category?cat_kewd={code}&page={page}&page_count=100&sort=RD"
        "&isAjaxRequest=0&type=job-category&is_param=1&isSearchResultEmpty=1&isSectionHome=0&searchParamCount=1")
ROLES = [("백엔드", "84"), ("데이터 엔지니어", "83")]   # 사람인 직무 키워드 코드: 백엔드/서버개발 84, 데이터엔지니어 83
PAGES = 3
SEED = 20261011
MAX_YEARS = 3
TRAINING = re.compile(r"교육생")   # 사람인 고용형태 '교육생' = 교육과정 모집(채용 공고 아님)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def min_years(career: str):
    """목록의 경력 조건 -> 최소 요구 연수(0 = 신입 가능). 경력만 적고 연수가 없으면 1로 본다(경력자면 지원 가능)."""
    if "신입" in career or "경력무관" in career:
        return 0
    m = re.search(r"경력\s*(\d+)\s*년", career) or re.search(r"(\d+)\s*~\s*\d+\s*년", career)
    if m:
        return int(m.group(1))
    return 1 if "경력" in career else None


def parse_list(page: str) -> list[dict]:
    out = []
    for rid, blk in re.findall(r'<div id="rec-(\d+)" class="list_item[^"]*">(.*?)<div class="similar_recruit">', page, re.S):
        t = re.search(r'id="rec_link_\d+"[^>]*title="([^"]*)"', blk)
        c = re.search(r'<div class="col company_nm">\s*<a[^>]*>\s*([^<]+?)\s*</a>', blk)
        car = re.search(r'<p class="career">\s*(.*?)\s*</p>', blk, re.S)
        sec = re.search(r'<span class="job_sector">(.*?)</span>\s*</div>', blk, re.S)
        out.append({"rec_idx": rid, "title": html.unescape(t.group(1)).strip() if t else "",
                    "company": html.unescape(c.group(1)).strip() if c else "",
                    "career": re.sub(r"\s+", " ", html.unescape(car.group(1))) if car else "",
                    "tags": ", ".join(re.findall(r"<span>([^<]+)</span>", sec.group(1))) if sec else ""})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="sample3")
    ap.add_argument("--per-role", type=int, default=10)
    args = ap.parse_args()
    out = os.path.join(HERE, args.out)
    os.makedirs(os.path.join(out, "pages"), exist_ok=True)
    norm_co = lambda s: re.sub(r"\(주\)|㈜|주식회사|유한회사|\s", "", s)
    used, used_co = set(), set()
    for f in (os.path.join(HERE, "targets.tsv"), os.path.join(HERE, "sample2", "targets.tsv")):
        for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"):
            used.add(r["rec_idx"]); used_co.add(norm_co(r["company"]))

    log, picked = [], []
    for role, code in ROLES:
        pool = []
        for p in range(1, PAGES + 1):
            st, _, b = get(LIST.format(code=code, page=p))
            items = parse_list(b.decode("utf-8", "replace")) if st == 200 else []
            for it in items:
                y = min_years(it["career"])
                ok = y is not None and y <= MAX_YEARS and not TRAINING.search(it["career"])
                log.append({"role": role, **it, "min_years": "" if y is None else y, "eligible": int(ok)})
                if ok and it["rec_idx"] not in used and norm_co(it["company"]) not in used_co:
                    pool.append(it)
            print(f"[{role}] 목록 {p}쪽: {len(items)}건", flush=True)
        rng = random.Random(f"{SEED}-{role}")
        rng.shuffle(pool)
        got = 0
        for it in pool:
            if got >= args.per_role:
                break
            if it["rec_idx"] in used or norm_co(it["company"]) in used_co:
                continue
            path = os.path.join(out, "pages", f"{it['rec_idx']}.html")
            if os.path.exists(path):
                page = open(path, encoding="utf-8").read()
            else:
                st, _, b = get(RELAY.format(id=it["rec_idx"]))
                page = b.decode("utf-8", "replace") if st == 200 else ""
                open(path, "w", encoding="utf-8").write(page)
            n_text, n_img = body_stats(page)
            if n_text < 0:  # 본문 칸이 없는 공고(외부 링크 등)는 건너뛴다
                continue
            kind = "이미지" if n_text < 100 and n_img >= 1 else ("글" if n_img == 0 else "섞임")
            picked.append({"rec_idx": it["rec_idx"], "company": it["company"], "title": it["title"], "role": role,
                           "career": it["career"], "kind": kind, "text_chars": n_text, "images": n_img})
            used.add(it["rec_idx"]); used_co.add(norm_co(it["company"]))
            got += 1
            print(f"   {it['rec_idx']} {kind:<3} 글자 {n_text:>5} 이미지 {n_img} | {it['career']} | {it['company']} | {it['title'][:40]}", flush=True)
        n_ok = sum(1 for r in log if r["role"] == role and r["eligible"])
        print(f"[{role}] 후보 {sum(1 for r in log if r['role'] == role)}건 중 0~{MAX_YEARS}년 {n_ok}건, 뽑음 {got}건", flush=True)

    with open(os.path.join(out, "targets.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(picked[0]), delimiter="\t")
        w.writeheader(); w.writerows(picked)
    with open(os.path.join(out, "sampling_log.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(log[0]), delimiter="\t")
        w.writeheader(); w.writerows(log)
    print(f"고른 공고 {len(picked)}건 -> {args.out}/targets.tsv")


if __name__ == "__main__":
    main()
