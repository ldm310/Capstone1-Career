"""
필수·우대 줄 묶기: embed_items.py 의 임베딩으로 비슷한 글끼리 묶는다(평균 연결 계층 군집, 코사인 거리).

  기준(거리) 아래에서만 묶는다 — 묶음 안 글끼리의 평균 유사도가 (1 - 기준) 이상. 기준이 작을수록 잘게 나뉜다.
  여러 기준으로 한 번에 자르고, 보기 파일에서 골라 볼 수 있다.
  결과: out/embed/<모델>/
          clusters.tsv   row · 글 · 줄 수 · 기준별 묶음 번호
          clusters.html  묶음 보기(로컬 전용 — 공고 글이라 밖에 올리지 않는다). 묶음은 줄 수가 많은 순.

실행: py -3.12 cluster_items.py [--model text-embedding-3-large] [--cuts 0.4,0.5,0.6]
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
from collections import defaultdict

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

HERE = os.path.dirname(os.path.abspath(__file__))
CHUNK = 2000


def condensed_cosine(v: np.ndarray) -> np.ndarray:
    """scipy linkage 가 받는 모양(위 삼각형을 한 줄로)의 코사인 거리. 행렬 전체를 한꺼번에 두지 않는다."""
    n = len(v)
    d = np.empty(n * (n - 1) // 2, dtype=np.float64)
    pos = 0
    for a in range(0, n, CHUNK):
        s = v[a:a + CHUNK] @ v.T
        for i in range(a, min(a + CHUNK, n)):
            row = s[i - a, i + 1:]
            d[pos:pos + len(row)] = 1.0 - row
            pos += len(row)
    np.clip(d, 0.0, 2.0, out=d)
    return d


def read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def build_groups(labels: np.ndarray, texts: list[dict], postings: list[set]) -> list[dict]:
    """묶음마다: 대표 글(가장 많이 나온 글) · 줄 수 · 필수/우대 · 공고 수 · 글 목록(많은 순)."""
    members = defaultdict(list)
    for r, c in enumerate(labels):
        members[int(c)].append(r)
    out = []
    for rows in members.values():
        rows.sort(key=lambda r: -texts[r]["n"])
        ps = set().union(*(postings[r] for r in rows))
        out.append({"rep": texts[rows[0]]["text"], "n": sum(texts[r]["n"] for r in rows),
                    "req": sum(texts[r]["필수"] for r in rows), "pref": sum(texts[r]["우대"] for r in rows),
                    "postings": len(ps), "rows": rows})
    out.sort(key=lambda g: (-g["n"], g["rep"]))
    return out


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>필수·우대 묶음</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#ddd;--soft:#f5f5f5;--mark:#fff3a8;--req:#b4232a;--pref:#1f5fbf}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Malgun Gothic",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;z-index:1}
h1{font-size:17px;margin:0 0 6px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.bar input{flex:1;min-width:200px;padding:6px 8px;border:1px solid #999;border-radius:4px;font:inherit}
.bar button{padding:5px 10px;border:1px solid #999;background:var(--bg);border-radius:4px;cursor:pointer;font:inherit}
.bar button.on{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.sum{color:var(--mute);font-size:13px;margin-top:6px}
main{padding:8px 16px 40px;max-width:1100px}
details{border:1px solid var(--line);border-radius:6px;margin:6px 0;background:var(--bg)}
summary{padding:8px 10px;cursor:pointer;display:flex;gap:10px;align-items:baseline}
summary .no{color:var(--mute);min-width:3.5em;font-variant-numeric:tabular-nums}
summary .rep{font-weight:600;flex:1}
summary .num{color:var(--mute);font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}
.peek{color:var(--mute);font-size:12px;padding:0 10px 8px 4.9em;margin-top:-4px}
ul{margin:0;padding:6px 10px 10px 4.9em;list-style:none;border-top:1px solid var(--line);background:var(--soft)}
li{padding:1px 0}
li .c{color:var(--mute);font-size:12px;margin-left:6px;font-variant-numeric:tabular-nums}
.r{color:var(--req)}.p{color:var(--pref)}
mark{background:var(--mark)}
.more{padding:10px 0;color:var(--mute)}
</style></head><body>
<header><h1>필수·우대 묶음 <small style="font-weight:400;color:var(--mute)">__MODEL__ · 평균 연결 군집</small></h1>
<div class="bar"><span>기준</span><span id="cuts"></span>
<input id="q" placeholder="글로 찾기 (예: Spring, 쿠버네티스, 학사)"></div>
<div class="sum" id="sum"></div></header>
<main id="list"></main>
<script>
const D = __DATA__;
const T = D.texts;   // [글, 줄 수, 필수, 우대]
let cut = D.default, q = "", shown = 150;
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const hl = s => { s = esc(s); if (!q) return s; const k = esc(q).replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
  return s.replace(new RegExp(k, "gi"), m => "<mark>" + m + "</mark>"); };
function render() {
  const G = D.groups[cut], ql = q.toLowerCase();
  const hit = q ? G.filter(g => g.rows.some(r => T[r][0].toLowerCase().includes(ql))) : G;
  const lines = G.reduce((a, g) => a + g.n, 0), single = G.filter(g => g.rows.length === 1).length;
  document.getElementById("sum").textContent =
    `묶음 ${G.length}개 (글 하나뿐인 묶음 ${single}개) · 글 ${T.length}개 · 줄 ${lines}개` +
    (q ? ` · '${q}' 들어간 묶음 ${hit.length}개` : "") +
    ` · 기준 ${cut}: 묶음 안 글끼리 평균 유사도 ${(1 - cut).toFixed(2)} 이상`;
  const el = document.getElementById("list");
  el.innerHTML = hit.slice(0, shown).map(g => {
    const no = G.indexOf(g) + 1;
    const peek = g.rows.slice(1, 6).map(r => esc(T[r][0])).join(" · ");
    return `<details><summary><span class="no">#${no}</span><span class="rep">${hl(g.rep)}</span>` +
      `<span class="num">줄 ${g.n} · 글 ${g.rows.length} · 공고 ${g.postings} · <span class="r">필수 ${g.req}</span> <span class="p">우대 ${g.pref}</span></span></summary>` +
      (peek ? `<div class="peek">${peek}${g.rows.length > 6 ? " …" : ""}</div>` : "") +
      `<ul data-rows="${g.rows.join(",")}"></ul></details>`;
  }).join("") + (hit.length > shown ? `<div class="more"><button onclick="shown+=300;render()">더 보기 (${hit.length - shown}개 남음)</button></div>` : "");
}
document.getElementById("list").addEventListener("toggle", e => {
  const ul = e.target.querySelector("ul");
  if (e.target.open && !ul.childElementCount)
    ul.innerHTML = ul.dataset.rows.split(",").map(Number).map(r =>
      `<li>${hl(T[r][0])}<span class="c">${T[r][1]}줄 · <span class="r">${T[r][2]}</span>/<span class="p">${T[r][3]}</span></span></li>`).join("");
}, true);
const cutsEl = document.getElementById("cuts");
D.cuts.forEach(c => { const b = document.createElement("button"); b.textContent = c + ` (${D.groups[c].length}개)`;
  b.onclick = () => { cut = c; shown = 150; [...cutsEl.children].forEach(x => x.classList.toggle("on", x === b)); render(); };
  if (c === cut) b.classList.add("on"); cutsEl.appendChild(b); cutsEl.append(" "); });
let timer; document.getElementById("q").addEventListener("input", e => { clearTimeout(timer);
  timer = setTimeout(() => { q = e.target.value.trim(); shown = 150; render(); }, 200); });
render();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="text-embedding-3-large")
    ap.add_argument("--cuts", default="0.4,0.5,0.6", help="쉼표로 여러 기준(코사인 거리)")
    ap.add_argument("--default", default="0.5", help="보기 파일에서 처음 고른 기준")
    args = ap.parse_args()
    cuts = [c.strip() for c in args.cuts.split(",") if c.strip()]
    default = args.default if args.default in cuts else cuts[0]

    d = os.path.join(HERE, "out", "embed", args.model)
    v = np.load(os.path.join(d, "vectors.npy")).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    texts = [{"text": r["text"], "n": int(r["n"]), "필수": int(r["필수"]), "우대": int(r["우대"])}
             for r in read_tsv(os.path.join(d, "texts.tsv"))]
    postings = [set() for _ in texts]
    for r in read_tsv(os.path.join(d, "items.tsv")):
        postings[int(r["row"])].add(r["posting_id"])
    print(f"글 {len(texts)}개 묶는 중 …", flush=True)

    z = linkage(condensed_cosine(v), method="average")
    labels = {c: fcluster(z, float(c), criterion="distance") for c in cuts}
    groups = {c: build_groups(labels[c], texts, postings) for c in cuts}

    with open(os.path.join(d, "clusters.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["row", "text", "n"] + [f"묶음@{c}" for c in cuts])
        # 묶음 번호는 보기 파일과 같게: 줄 수 많은 순 1, 2, 3 …
        rank = {c: {r: i + 1 for i, g in enumerate(groups[c]) for r in g["rows"]} for c in cuts}
        for r, t in enumerate(texts):
            w.writerow([r, t["text"], t["n"]] + [rank[c][r] for c in cuts])

    data = {"cuts": cuts, "default": default,
            "texts": [[t["text"], t["n"], t["필수"], t["우대"]] for t in texts],
            "groups": {c: [{k: g[k] for k in ("rep", "n", "req", "pref", "postings", "rows")} for g in groups[c]] for c in cuts}}
    page = (PAGE.replace("__MODEL__", html.escape(args.model))
                .replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
    out = os.path.join(d, "clusters.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)

    for c in cuts:
        g = groups[c]
        print(f"기준 {c}: 묶음 {len(g)}개 (글 하나뿐 {sum(len(x['rows']) == 1 for x in g)}개)")
    print(f"보기: {out}")


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
