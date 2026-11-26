"""
공고 카테고리(팀원 7개판): 공고의 필수·우대 줄에 붙은 기술 카테고리를 모아 공고에 붙인다.

  기준(2026-11-26 회의·사용자 결정): 기술 7개 = 프로그래밍·CS 기초 / 백엔드 개발 / 데이터베이스 / 데이터 엔지니어링·분석 /
      인프라·배포·운영 / 프론트엔드·앱 개발 / AI 기술. 원본은 팀원이 보낸 career-embedding-analysis.html(문장 7,595개).
  1) 팀원 결과에 있는 줄: 팀원이 붙인 카테고리를 그대로 쓴다(공백만 정리하고 글자가 같아야 함).
  2) 없는 줄: LLM 이 팀원 예시를 보고 같은 방식으로 붙인다. 애매하면 '확인 필요'(unsure)를 남긴다.
  3) 공고마다 기술 카테고리만 모은다(기타·도구·업종·지원 조건·제외는 공고에 붙이지 않음).
  다시 돌리면: 같은 지시문으로 이미 붙인 글은 건너뛴다(llm_labels.jsonl).
  결과: out/team_categories/   (로컬 전용 — 공고 글이라 밖에 올리지 않는다)
          llm_labels.jsonl        LLM 이 붙인 글 · 카테고리 · 확인 필요 · 지시문 버전
          llm_labels.html         LLM 이 붙인 글 보기
          posting_categories.tsv  공고 · 기술 카테고리 · 줄 수
  --apply 면 공고 표 posting.skill_categories 에 쓴다(011 마이그레이션 필요). 없으면 파일만.
      백엔드·데이터 공고는 코드 목록(없으면 {}), 그 외 자리만 있는 공고는 NULL(대상 아님).
  Airflow: 두 DAG 의 '카테고리 붙이기' 태스크가 DB 저장 뒤에 update(apply=True) 를 부른다(새 글만 LLM).
      Airflow 는 이 폴더를 그대로 쓰므로 out/team_categories/ 의 팀원 파일·LLM 결과를 같이 본다.

실행: py -3.12 team_categories.py --dry-run     # LLM 없이 규모만
      py -3.12 team_categories.py --sample 100  # 시험: 글 100개만 LLM
      py -3.12 team_categories.py               # 전부(파일만)
      py -3.12 team_categories.py --apply       # 전부 + 공고 표에 쓰기
환경변수 OPENAI_API_KEY 필요. DB 는 db_load.connect() 와 같음(--apply 가 아니면 읽기만 한다).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "team_categories")
TEAM_HTML = os.path.join(OUT, "career-embedding-analysis.html")
PRICES = {"gpt-5.6-luna": (0.20, 1.20), "gpt-5.6-terra": (2.00, 12.00)}  # USD/1M (입력, 출력)
BATCH = 100
TARGET_JOBS = ("백엔드", "데이터 엔지니어")

TECH = [  # 코드, 이름(팀원 페이지와 같음), 설명
    ("L", "프로그래밍·CS 기초", "프로그래밍 언어(Java, Python, C#, C/C++, JavaScript/TypeScript, Go, Kotlin, PHP)와 CS 기초(자료구조·알고리즘, 운영체제, 네트워크·HTTP 원리, 객체지향)"),
    ("B", "백엔드 개발", "서버 프레임워크(Spring·JPA, FastAPI·Django, Node.js·NestJS, .NET), REST API·외부 시스템 연동, Redis 캐시·메시지 큐, MSA·대용량 트래픽, 결제·주문 같은 서버 기능, 백엔드·서버 개발 경험"),
    ("D", "데이터베이스", "SQL, RDBMS(MySQL·PostgreSQL·Oracle), NoSQL, DB 설계·데이터 모델링, 쿼리 튜닝, 트랜잭션·인덱스, 검색 엔진"),
    ("E", "데이터 엔지니어링·분석", "데이터 파이프라인·ETL, Airflow, Spark·Databricks, 스트리밍, 크롤링·데이터 수집, 데이터 분석·통계"),
    ("O", "인프라·배포·운영", "AWS·GCP·Azure, Linux 서버, Docker·Kubernetes, CI/CD·배포 자동화, 모니터링·로그, 장애 대응, 서비스 운영"),
    ("F", "프론트엔드·앱 개발", "React·Vue·Next.js, HTML/CSS, 웹 화면·관리자 화면, 모바일 앱(iOS·Android·Flutter·React Native)"),
    ("A", "AI 기술", "AI 코딩 도구 활용, LLM API 연동, RAG·벡터 검색, LangChain·에이전트, 머신러닝 모델"),
]
OTHER = [  # 기술 카테고리가 아닌 표시 — 공고에는 붙이지 않는다
    ("OTHER", "기타", "위 7개에 들지 않는 개발·업무 능력(코드 리뷰·테스트, 보안, 요구사항 분석·문서화, 기존 코드 분석, SI·솔루션 개발, 장비 연동 등)"),
    ("T", "도구·개발 방식", "Git·형상관리, Jira·Notion 같은 협업 도구, 애자일"),
    ("M", "업종·업무 경험", "금융·커머스·의료·제조·공공 같은 업종이나 업무 도메인 경험"),
    ("X", "지원 조건", "학력·전공, 기술 없는 연차·경력, 자격증, 외국어, 근무 조건, 포트폴리오 제출"),
    ("EXCLUDED", "제외", "구체적으로 해 본 근거가 없는 태도·관심·소프트 스킬(소통, 협업 태도, 학습 의지, 책임감, '~에 대한 관심')"),
]
TECH_CODES = [c for c, _, _ in TECH]
CODES = TECH_CODES + [c for c, _, _ in OTHER]
NAME = {c: n for c, n, _ in TECH + OTHER}


def norm(text: str) -> str:
    """팀원 API 와 같은 맞춤: NFC + 공백 하나로."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def load_team(path: str = TEAM_HTML) -> dict[str, list[str]]:
    """팀원 7개판 → {정리한 글: 코드}. 제외된 글은 ['EXCLUDED']."""
    if not os.path.exists(path):   # 로컬 전용 파일(공고 글이라 저장소에 없음) — Airflow 폴더를 옮기면 같이 옮겨야 한다
        raise FileNotFoundError(f"팀원 7개판 파일이 없습니다: {path} — out/team_categories/ 에 career-embedding-analysis.html 을 두세요")
    src = open(path, encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="presentation-data">(.*?)</script>', src, re.S)
    team = {}
    for r in json.loads(m.group(1))["rows"]:
        codes = ["EXCLUDED"] if r["excluded"] else [c for c in CODES if c in r["categories"]]
        key = norm(r["text"])
        if key in team and team[key] != codes:
            raise ValueError(f"같은 글에 다른 분류: {key}")
        team[key] = codes
    return team


def examples(team: dict[str, list[str]], per: int = 8) -> list[tuple[str, list[str]]]:
    """표시마다 팀원 예시 몇 개(고정 시드라 지시문이 매번 같다)."""
    rng, out, used = random.Random(7), [], set()
    for code in CODES:
        pool = sorted(t for t, c in team.items() if code in c and t not in used)
        for t in rng.sample(pool, min(per, len(pool))):
            used.add(t)
            out.append((t, team[t]))
    return out


def build_instructions(team: dict[str, list[str]]) -> str:
    ex = "\n".join(f"- {t} → {', '.join(c)}" for t, c in examples(team))
    return f"""너는 백엔드·데이터 엔지니어 채용공고의 필수·우대 줄마다 카테고리를 붙인다. 아래 팀 예시와 같은 방식으로 붙인다.

기술 카테고리:
{chr(10).join(f"- {c}: {n} — {d}" for c, n, d in TECH)}

기술이 아닌 표시:
{chr(10).join(f"- {c}: {n} — {d}" for c, n, d in OTHER)}

규칙:
- 해당하는 것을 모두 고른다. 보통 1~3개. 억지로 늘리지 않는다.
- 언어 이름이 적혀 있으면 L 도 고른다. 프레임워크만 적혀 있으면 L 을 붙이지 않는다(예: 'Spring Boot 사용 경험' → B).
- 기술과 업종이 함께 있으면 둘 다 고른다.
- 보안·인증·인가·암호화·개인정보 보호는 OTHER 다(B 가 아님). 다른 기술과 함께 있으면 그 기술도 고른다(예: 'REST API 개발 및 인증·권한 처리 경험' → B, OTHER).
- EXCLUDED 는 다른 것과 함께 쓰지 않는다.
- 판단이 애매하면 가장 맞는 것을 고르고 unsure 를 true 로 둔다.
- 입력의 줄마다 id 를 그대로 돌려준다. 모든 줄에 답한다.

팀 예시:
{ex}"""


SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "cats", "unsure"],
        "properties": {"id": {"type": "integer"},
                       "cats": {"type": "array", "items": {"type": "string", "enum": CODES}},
                       "unsure": {"type": "boolean"}}}}},
}


def prompt_version(instructions: str) -> str:
    return hashlib.sha256((instructions + json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:12]


def clean(cats: list[str]) -> list[str]:
    cats = sorted(set(cats), key=CODES.index)
    return [c for c in cats if c != "EXCLUDED"] if len(cats) > 1 else cats


def current_lines(conn) -> list[tuple[int, str, str]]:
    """현재 결과의 백엔드·데이터 엔지니어 자리 필수·우대 줄 → (공고, 필수/우대, 글)."""
    return conn.execute(
        """SELECT r.posting_id, i.category, i.text
             FROM unit_item i JOIN recruit_unit u ON u.id = i.unit_id
             JOIN extraction_run r ON r.id = u.run_id
            WHERE r.is_current AND i.category IN ('필수', '우대') AND u.job = ANY(%s)""",
        (list(TARGET_JOBS),)).fetchall()


def load_done(path: str, version: str) -> dict[str, dict]:
    done = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            r = json.loads(ln)
            if r["prompt"] == version:
                done[r["text"]] = r
    return done


def classify(client, model: str, effort: str, instructions: str, texts: list[str]) -> tuple[dict[str, dict], int, int]:
    """글 묶음 한 번 → {글: {cats, unsure}}. 빠진 줄은 한 번 더 묻는다."""
    out, tin, tout, todo = {}, 0, 0, list(texts)
    for _ in range(2):
        resp = client.responses.create(
            model=model, instructions=instructions, input="\n".join(f"{i}\t{t}" for i, t in enumerate(todo)),
            max_output_tokens=16000, reasoning={"effort": effort},
            text={"format": {"type": "json_schema", "name": "categories", "schema": SCHEMA, "strict": True}})
        tin += resp.usage.input_tokens
        tout += resp.usage.output_tokens
        for it in json.loads(resp.output_text)["items"]:
            if 0 <= it["id"] < len(todo) and it["cats"]:
                out[todo[it["id"]]] = {"cats": clean(it["cats"]), "unsure": it["unsure"]}
        todo = [t for t in todo if t not in out]
        if not todo:
            break
    return out, tin, tout


def posting_categories(lines, team: dict[str, list[str]], llm: dict[str, dict]) -> dict[int, dict]:
    """공고마다 기술 카테고리(7개 중) 모으기 + 줄 출처 세기."""
    P = defaultdict(lambda: {"codes": set(), "lines": 0, "team": 0, "llm": 0, "unsure": 0, "missing": 0})
    for pid, _cat, text in lines:
        p, key = P[pid], norm(text)
        p["lines"] += 1
        if key in team:
            cats = team[key]
            p["team"] += 1
        elif key in llm:
            cats = llm[key]["cats"]
            p["llm"] += 1
            p["unsure"] += llm[key]["unsure"]
        else:
            p["missing"] += 1
            continue
        p["codes"] |= {c for c in cats if c in TECH_CODES}
    return P


def save(conn, P: dict[int, dict]) -> int:
    """posting.skill_categories 채우기. 현재 추출 결과가 있는 공고만 본다(2026-11-27 사용자 결정).
      백엔드·데이터 자리가 있는 공고: 모은 기술 코드, 하나도 없으면 {}(봤는데 붙일 기술 없음).
      그 외 자리만 있는(직무 거르기에서 빠진) 공고·자리가 없는 공고: NULL(대상 아님).
    분류 못 한 줄이 남은 공고는 건너뛴다(덜 붙은 채로 쓰지 않음). 값이 바뀐 공고만 쓰고, 쓴 수를 돌려준다."""
    found = conn.execute("""SELECT r.posting_id, coalesce(bool_or(u.job = ANY(%s)), false)
                            FROM extraction_run r LEFT JOIN recruit_unit u ON u.run_id = r.id
                            WHERE r.is_current GROUP BY r.posting_id""", (list(TARGET_JOBS),)).fetchall()
    rows = []
    for pid, target in found:
        p = P.get(pid)
        if p and p["missing"]:
            continue
        rows.append(([c for c in TECH_CODES if p and c in p["codes"]] if target else None, pid))
    n = 0
    with conn.transaction():
        for codes, pid in rows:
            n += conn.execute("UPDATE posting SET skill_categories = %s WHERE id = %s AND skill_categories IS DISTINCT FROM %s",
                              (codes, pid, codes)).rowcount
    return n


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LLM 분류 확인</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#ddd;--soft:#f0f0f0;--warn:#b4232a}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Malgun Gothic",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px}
h1{font-size:17px;margin:0 0 8px}
.f{display:flex;flex-wrap:wrap;gap:6px}
.f button{padding:3px 9px;border:1px solid #999;background:var(--bg);border-radius:12px;cursor:pointer;font:inherit;font-size:13px}
.f button.on{background:var(--fg);color:var(--bg);border-color:var(--fg)}
main{padding:8px 16px 40px;max-width:1000px}
.row{display:flex;gap:10px;padding:5px 0;border-bottom:1px solid var(--line);align-items:baseline}
.row .t{flex:1}
.tag{display:inline-block;font-size:12px;padding:0 7px;border-radius:10px;background:var(--soft);margin-left:4px;white-space:nowrap}
.u{color:var(--warn);font-size:12px;margin-left:6px}
</style></head><body>
<header><h1>LLM 분류 확인 <small style="font-weight:400;color:var(--mute)">팀원 7개판 예시 · 지시문 __PROMPT__</small></h1>
<div class="f" id="f"></div></header><main id="list"></main>
<script>
const N = __NAMES__, R = __ROWS__;  // R: [글, [코드…], 확인 필요]
let pick = "";
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function render() {
  const rows = R.filter(r => !pick || (pick === "?" ? r[2] : r[1].includes(pick)));
  document.getElementById("list").innerHTML = rows.map(r => `<div class="row"><span class="t">${esc(r[0])}</span><span>${r[1].map(c => `<span class="tag">${N[c]}</span>`).join("")}${r[2] ? '<span class="u">확인 필요</span>' : ""}</span></div>`).join("");
}
const f = document.getElementById("f");
[["", "전체", R.length], ["?", "확인 필요", R.filter(r => r[2]).length], ...Object.keys(N).map(c => [c, N[c], R.filter(r => r[1].includes(c)).length])].forEach(([k, n, m]) => {
  const b = document.createElement("button"); b.textContent = `${n} ${m}`; if (!k) b.classList.add("on");
  b.onclick = () => { pick = k; [...f.children].forEach(x => x.classList.toggle("on", x === b)); render(); }; f.appendChild(b); });
render();
</script></body></html>
"""


def update(apply: bool = False, model: str = "gpt-5.6-luna", effort: str = "low", workers: int = 4,
           sample: int = 0, dry_run: bool = False) -> dict:
    """한 번 돌리기 — 명령줄과 Airflow '카테고리 붙이기' 태스크(pipeline_tasks.step_categories)가 같이 쓴다.
    현재 결과의 줄을 RDS 에서 읽고, 팀원 결과·지난 LLM 결과에 없는 글만 LLM 에 보낸 뒤, apply 면 공고 표에 쓴다.
    돌려주는 것: {"공고": 줄이 있는 공고 수, "새 글": 이번에 LLM 에 보낸 글 수, "비용": USD,
                  "못 붙인 공고": 분류 못 한 줄이 남아 건너뛴 공고 수(다음에 다시), "고침": 공고 표에서 값이 바뀐 공고 수}"""
    import db_load
    team = load_team()
    instructions = build_instructions(team)
    version = prompt_version(instructions)
    with db_load.connect() as conn:
        lines = current_lines(conn)

    os.makedirs(OUT, exist_ok=True)
    labels_path = os.path.join(OUT, "llm_labels.jsonl")
    done = load_done(labels_path, version)
    missing = sorted({norm(t) for _p, _c, t in lines} - set(team))
    todo = [t for t in missing if t not in done]
    if sample:
        todo = random.Random(1).sample(todo, min(sample, len(todo)))
    print(f"팀원 결과 글 {len(team)}개 · 지금 줄 {len(lines)}개 · 팀원 결과에 없는 글 {len(missing)}개 · "
          f"이미 붙임 {len(missing) - len([t for t in missing if t not in done])}개 · 이번에 보낼 글 {len(todo)}개 · 지시문 {version}")

    usd = 0.0
    if todo and not dry_run:
        from openai import OpenAI
        client = OpenAI(max_retries=4, timeout=300)
        chunks = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
        tin = tout = 0
        with ThreadPoolExecutor(workers) as ex, open(labels_path, "a", encoding="utf-8") as f:
            futs = [ex.submit(classify, client, model, effort, instructions, ch) for ch in chunks]
            for n, fut in enumerate(as_completed(futs), 1):
                got, a, b = fut.result()
                tin, tout = tin + a, tout + b
                for t, r in got.items():
                    rec = {"text": t, **r, "prompt": version, "model": model}
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    done[t] = rec
                f.flush()
                print(f"  묶음 {n}/{len(chunks)}", flush=True)
        pin, pout = PRICES.get(model, (0, 0))
        usd = round((tin * pin + tout * pout) / 1e6, 6)
        print(f"토큰 입력 {tin} · 출력 {tout} · 약 ${usd:.3f}")

    llm = {t: done[t] for t in missing if t in done}
    P = posting_categories(lines, team, llm)
    with open(os.path.join(OUT, "posting_categories.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["posting_id", "codes", "categories", "lines", "team_lines", "llm_lines", "unsure_lines", "missing_lines"])
        for pid in sorted(P):
            p = P[pid]
            codes = [c for c in TECH_CODES if c in p["codes"]]
            w.writerow([pid, ",".join(codes), " · ".join(NAME[c] for c in codes), p["lines"], p["team"], p["llm"], p["unsure"], p["missing"]])

    rows = [[t, llm[t]["cats"], llm[t]["unsure"]] for t in sorted(llm)]
    page = (PAGE.replace("__PROMPT__", version)
                .replace("__NAMES__", json.dumps(NAME, ensure_ascii=False))
                .replace("__ROWS__", json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")))
    open(os.path.join(OUT, "llm_labels.html"), "w", encoding="utf-8").write(page)

    full = [p for p in P.values() if not p["missing"]]
    dist = Counter(len(p["codes"]) for p in P.values())
    share = Counter(c for p in P.values() for c in p["codes"])
    print(f"공고 {len(P)}개 · 줄이 다 분류된 공고 {len(full)}개 · LLM 확인 필요 글 {sum(r[2] for r in rows)}개")
    print("공고당 카테고리 수: " + " ".join(f"{k}개 {dist[k]}" for k in sorted(dist)))
    print("카테고리가 붙은 공고 비율: " + " · ".join(f"{NAME[c]} {share[c] * 100 // max(len(P), 1)}%" for c in TECH_CODES))
    print(f"보기: {os.path.join(OUT, 'llm_labels.html')}")
    stats = {"공고": len(P), "새 글": 0 if dry_run else len(todo), "비용": usd, "못 붙인 공고": len(P) - len(full), "고침": 0}
    if apply and not dry_run:
        with db_load.connect() as conn:
            stats["고침"] = save(conn, P)
        print(f"공고 표에 씀: {stats['고침']}개")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--sample", type=int, default=0, help="LLM 에 보낼 글 수(시험)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true", help="LLM 없이 규모만")
    ap.add_argument("--apply", action="store_true", help="공고 표 skill_categories 에 쓴다(없으면 파일만)")
    a = ap.parse_args()
    update(apply=a.apply, model=a.model, effort=a.effort, workers=a.workers, sample=a.sample, dry_run=a.dry_run)


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
