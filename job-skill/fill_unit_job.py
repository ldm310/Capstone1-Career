"""
이미 추출한 자리(모집 단위)에 직무(백엔드 / 데이터 엔지니어 / 그 외)를 채운다 — 2026-11-12 전에 추출해 job 칸이 빈 자리.
새로 추출하는 자리는 추출 LLM 이 직무를 정하므로 이 스크립트가 필요 없다(같은 규칙 JOB_RULE 을 쓴다).

  IT 가 아닌 자리: LLM 없이 '그 외'.
  IT 자리(현재 사용 중인 추출 결과만): 자리 이름 + 공고 제목 + 업무·필수·우대 몇 줄을 LLM 에 보내 직무를 고르게 한다.
    자리 이름에 직무가 적히지 않은 경우가 많아(82%) 내용으로 판단한다.
  고른 직무는 out/fill_unit_job/<모델>/decisions.jsonl 에 남겨 다시 돌려도 돈을 다시 내지 않는다.
  '그 외' 자리의 한 줄은 DB 에서 지우지 않는다(웹 화면용) — 카테고리·레벨 계산에서만 뺀다.

실행: py -3.12 fill_unit_job.py --dry-run     # DB 에 쓰지 않고 결과만 보기(직무 칸이 아직 없어도 됨)
      py -3.12 fill_unit_job.py               # DB 에 쓰기(마이그레이션 008 적용 뒤)
환경변수 OPENAI_API_KEY 필요. DB 는 db_load.connect() 와 같음(RDS 설정이 있으면 RDS).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import db_load
from extract_skills import JOB_RULE, JOBS, PRICES

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = 25
MAX_LINES = 10   # 자리마다 보내는 한 줄 수(업무 → 필수 → 우대 순)

INSTRUCTIONS = f"""너는 개발자 채용공고의 모집 단위(자리)마다 직무를 고른다.
입력은 자리마다 'id / 자리 이름 / 공고 제목 / 그 자리의 업무·필수·우대 몇 줄'이다.

{JOB_RULE}

모든 자리에 답하고 id 는 그대로 돌려준다."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["units"],
    "properties": {"units": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "job"],
        "properties": {"id": {"type": "integer"}, "job": {"type": "string", "enum": JOBS}}}}},
}
PROMPT_VERSION = hashlib.sha256((INSTRUCTIONS + json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:12]


def has_job_column(conn) -> bool:
    return conn.execute("""SELECT 1 FROM information_schema.columns
                           WHERE table_schema = 'public' AND table_name = 'recruit_unit' AND column_name = 'job'""").fetchone() is not None


def load_units(conn, with_job: bool) -> list[dict]:
    """직무를 정할 IT 자리(현재 사용 중인 결과, 직무가 빈 것)와 그 자리의 한 줄들."""
    rows = conn.execute(f"""
        SELECT ru.id, ru.name, p.title
        FROM recruit_unit ru JOIN extraction_run er ON er.id = ru.run_id JOIN posting p ON p.id = er.posting_id
        WHERE er.is_current AND ru.is_it {"AND ru.job IS NULL" if with_job else ""}
        ORDER BY ru.id""").fetchall()
    lines = defaultdict(list)
    for uid, cat, text in conn.execute("""
            SELECT ui.unit_id, ui.category, ui.text
            FROM unit_item ui JOIN recruit_unit ru ON ru.id = ui.unit_id JOIN extraction_run er ON er.id = ru.run_id
            WHERE er.is_current AND ru.is_it AND ui.category IN ('업무', '필수', '우대')
            ORDER BY ui.unit_id, CASE ui.category WHEN '업무' THEN 0 WHEN '필수' THEN 1 ELSE 2 END, ui.seq""").fetchall():
        if len(lines[uid]) < MAX_LINES:
            lines[uid].append(f"[{cat}] {text[:80]}")
    return [{"id": uid, "name": name, "title": title, "lines": lines[uid]} for uid, name, title in rows]


def ask(client, model: str, effort: str, units: list[dict]) -> tuple[dict[int, str], int, int]:
    """자리 묶음 → {자리ID: 직무}. 빠진 자리는 한 번 더 묻는다."""
    out, tin, tout = {}, 0, 0
    todo = list(units)
    for _ in range(2):
        inp = "\n\n".join(f"id {i}\n자리 이름: {u['name']}\n공고 제목: {u['title']}\n" + "\n".join(u["lines"] or ["(줄 없음)"])
                          for i, u in enumerate(todo))
        resp = client.responses.create(
            model=model, instructions=INSTRUCTIONS, input=inp, max_output_tokens=4000, reasoning={"effort": effort},
            text={"format": {"type": "json_schema", "name": "jobs", "schema": SCHEMA, "strict": True}})
        tin += resp.usage.input_tokens
        tout += resp.usage.output_tokens
        for it in json.loads(resp.output_text)["units"]:
            if 0 <= it["id"] < len(todo):
                out[todo[it["id"]]["id"]] = it["job"]
        todo = [u for u in todo if u["id"] not in out]
        if not todo:
            break
    return out, tin, tout


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>자리별 직무</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#ddd;--soft:#f5f5f5;--be:#2f5f8f;--de:#2f7f5f;--ot:#999}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Malgun Gothic",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;z-index:1}
h1{font-size:17px;margin:0 0 8px}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.bar button{padding:3px 10px;border:1px solid #999;background:var(--bg);border-radius:12px;cursor:pointer;font:inherit;font-size:13px}
.bar button.on{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.bar input{flex:1;min-width:180px;padding:5px 8px;border:1px solid #999;border-radius:4px;font:inherit}
.sum{color:var(--mute);font-size:13px;margin-top:8px}
main{padding:6px 16px 40px;max-width:1100px}
details{border-bottom:1px solid var(--line)}
summary{padding:6px 0;cursor:pointer;display:flex;gap:10px;align-items:baseline}
.job{font-size:12px;color:#fff;border-radius:10px;padding:0 8px;white-space:nowrap;min-width:5.5em;text-align:center}
.job.백엔드{background:var(--be)}.job.데이터{background:var(--de)}.job.그{background:var(--ot)}
.nm{font-weight:600}.tt{color:var(--mute);font-size:12px}
ul{margin:0 0 8px;padding:6px 10px 8px 7.5em;list-style:none;background:var(--soft)}
li{font-size:13px}
.more{padding:10px 0}
</style></head><body>
<header><h1>자리별 직무 <small style="font-weight:400;color:var(--mute)">__MODEL__ · 지시문 __PROMPT__ · 줄을 누르면 그 자리의 업무·필수·우대(최대 10줄)</small></h1>
<div class="bar" id="bar"></div>
<div class="bar" style="margin-top:6px"><input id="q" placeholder="자리 이름·공고 제목·줄에서 찾기"></div>
<div class="sum" id="sum"></div></header>
<main id="list"></main>
<script>
const R = __ROWS__;   // [직무, 자리 이름, 공고 제목, [줄…]]
const NAME_HINT = /백엔드|백앤드|backend|back-end|서버|server|데이터|data/i;
const F = [["전체", r => true], ["백엔드", r => r[0] === "백엔드"], ["데이터 엔지니어", r => r[0] === "데이터 엔지니어"], ["그 외", r => r[0] === "그 외"],
           ["이름엔 백엔드·서버·데이터인데 그 외", r => r[0] === "그 외" && NAME_HINT.test(r[1])],
           ["이름엔 그런 말이 없는데 남김", r => r[0] !== "그 외" && !NAME_HINT.test(r[1])]];
let pick = 0, q = "", shown = 200;
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function render() {
  const ql = q.toLowerCase();
  const rows = R.filter(F[pick][1]).filter(r => !q || (r[1] + " " + r[2] + " " + r[3].join(" ")).toLowerCase().includes(ql));
  document.getElementById("sum").textContent = `자리 ${rows.length}개 / IT 자리 ${R.length}개`;
  document.getElementById("list").innerHTML = rows.slice(0, shown).map(r =>
    `<details><summary><span class="job ${r[0].split(" ")[0]}">${esc(r[0])}</span><span class="nm">${esc(r[1])}</span><span class="tt">${esc(r[2])}</span></summary>` +
    `<ul>${(r[3].length ? r[3] : ["(줄 없음)"]).map(l => `<li>${esc(l)}</li>`).join("")}</ul></details>`).join("") +
    (rows.length > shown ? `<div class="more"><button onclick="shown+=400;render()">더 보기 (${rows.length - shown}개 남음)</button></div>` : "");
}
const bar = document.getElementById("bar");
F.forEach(([n, f], i) => { const b = document.createElement("button"); b.textContent = `${n} ${R.filter(f).length}`; if (i === pick) b.classList.add("on");
  b.onclick = () => { pick = i; shown = 200; [...bar.children].forEach(x => x.classList.toggle("on", x === b)); render(); }; bar.appendChild(b); });
let t; document.getElementById("q").addEventListener("input", e => { clearTimeout(t); t = setTimeout(() => { q = e.target.value.trim(); shown = 200; render(); }, 200); });
render();
</script></body></html>
"""


def write_page(path: str, model: str, units: list[dict], decided: dict[int, str]) -> None:
    """자리별 직무 보기(로컬 전용 — 공고 글이라 밖에 올리지 않는다)."""
    import html as _html
    order = {j: k for k, j in enumerate(JOBS)}
    rows = sorted(([decided[u["id"]], u["name"], u["title"], u["lines"]] for u in units if u["id"] in decided),
                  key=lambda r: (order[r[0]], r[1]))
    page = (PAGE.replace("__MODEL__", _html.escape(model)).replace("__PROMPT__", PROMPT_VERSION)
                .replace("__ROWS__", json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않고 결과만 보기")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    d = os.path.join(HERE, "out", "fill_unit_job", args.model)
    os.makedirs(d, exist_ok=True)
    cache_path = os.path.join(d, "decisions.jsonl")
    cache: dict[int, str] = {}
    if os.path.exists(cache_path):
        for ln in open(cache_path, encoding="utf-8"):
            r = json.loads(ln)
            if r["prompt"] == PROMPT_VERSION:
                cache[r["unit_id"]] = r["job"]

    with db_load.connect() as conn:
        with_job = has_job_column(conn)
        if not with_job and not args.dry_run:
            sys.exit("recruit_unit.job 칸이 없습니다. 먼저 마이그레이션 008 을 적용하세요(py -3.12 db_load.py migrate).")
        units = load_units(conn, with_job)
        non_it = conn.execute(f"""SELECT count(*) FROM recruit_unit WHERE NOT is_it
                                  {"AND job IS NULL" if with_job else ""}""").fetchone()[0]
    todo = [u for u in units if u["id"] not in cache]
    print(f"IT 자리 {len(units)}개 (이미 정한 것 {len(units) - len(todo)}개, 새로 {len(todo)}개) · IT 아닌 자리 {non_it}개는 '그 외' · 지시문 {PROMPT_VERSION}", flush=True)

    tin = tout = 0
    if todo:
        from openai import OpenAI
        client = OpenAI(max_retries=4, timeout=300)
        batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
        t0 = time.perf_counter()
        with ThreadPoolExecutor(args.workers) as pool, open(cache_path, "a", encoding="utf-8") as f:
            futs = [pool.submit(ask, client, args.model, args.effort, b) for b in batches]
            for k, fu in enumerate(as_completed(futs), 1):
                got, i, o = fu.result()
                tin += i
                tout += o
                for uid, job in got.items():
                    cache[uid] = job
                    f.write(json.dumps({"unit_id": uid, "job": job, "prompt": PROMPT_VERSION}, ensure_ascii=False) + "\n")
                f.flush()
                if k % 10 == 0 or k == len(batches):
                    print(f"  {k}/{len(batches)}  {time.perf_counter() - t0:.0f}s", flush=True)
    pin, pout = PRICES.get(args.model, (0, 0))
    print(f"토큰 입력 {tin} 출력 {tout}  약 ${tin / 1e6 * pin + tout / 1e6 * pout:.4f}")

    decided = {u["id"]: cache[u["id"]] for u in units if u["id"] in cache}
    print("IT 자리 직무:", " · ".join(f"{j} {n}" for j, n in Counter(decided.values()).most_common()),
          f"· 답 없음 {len(units) - len(decided)}")
    name = {u["id"]: u["name"] for u in units}
    for job in JOBS:
        ex = [name[i] for i, j in decided.items() if j == job][:8]
        print(f"  {job} 예: " + " / ".join(ex))
    page = os.path.join(d, "jobs.html")
    write_page(page, args.model, units, decided)
    print(f"보기: {page}")
    if args.dry_run:
        print("--dry-run: DB 에 쓰지 않음")
        return

    with db_load.connect() as conn:
        n_non = conn.execute("UPDATE recruit_unit SET job = '그 외' WHERE NOT is_it AND job IS NULL").rowcount
        with conn.cursor() as cur:
            cur.executemany("UPDATE recruit_unit SET job = %s WHERE id = %s AND job IS NULL",
                            [(j, i) for i, j in decided.items()])
        print(f"DB: IT 아닌 자리 {n_non}개 '그 외', IT 자리 {len(decided)}개 직무 채움")


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
