"""
③ 필수·우대 줄마다 카테고리 붙이기: LLM 이 줄 하나에 맞는 카테고리를 모두 고른다(한 줄에 여러 개 가능).

  카테고리: 아래 CATEGORIES (개발 8 + 공통 2 + 지원 조건). 지원 조건은 묶음으로 두되 레벨은 매기지 않는다.
  개발 일반: 영역이 없는 줄('개발 경험')은 LLM 이 G 로 답하고, 그 줄이 나온 자리의 직무 카테고리로 바꾼다.
  입력: out/embed/<임베딩 모델>/items.tsv 의 원래 글(서로 다른 글만). 연차가 붙어 있어도 원래 글 그대로 보낸다.
  다시 돌리면: 같은 지시문으로 이미 붙인 글은 건너뛴다(labels.jsonl).
  결과: out/classify/<모델>/
          labels.jsonl  글 · 카테고리 · 지시문 버전
          labels.html   카테고리별 보기(로컬 전용 — 공고 글이라 밖에 올리지 않는다)

실행: py -3.12 classify_items.py --sample 300      # 시험: 줄 300개만
      py -3.12 classify_items.py                   # 전부
환경변수 OPENAI_API_KEY 필요.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import random
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
PRICES = {"gpt-5.6-luna": (0.20, 1.20), "gpt-5.6-terra": (2.00, 12.00)}  # USD/1M (입력, 출력)
BATCH = 100

# 코드, 이름, 묶음(개발/공통/애매/조건), 설명 — 백엔드·데이터 엔지니어 자리 기준(2026-11-12 사용자 결정: 개발 8 + 공통 2 + 지원 조건).
# 지원 조건은 묶음으로 두되 레벨은 매기지 않는다. 개발 일반(G)은 그 줄이 나온 자리의 직무 카테고리로 바꾼다(JOB_CATEGORY).
CATEGORIES = [
    ("L", "프로그래밍 기초", "개발", "언어 자체를 쓰는 능력(Java, Python, C#, C/C++, JavaScript/TypeScript, Go, Kotlin, PHP, Shell 스크립트)과 "
          "CS 기초(자료구조·알고리즘, 운영체제, HTTP·네트워크 동작 원리, 객체지향·함수형 개념)"),
    ("B", "백엔드 개발", "개발", "서버 프레임워크(Spring·JPA·MyBatis, FastAPI·Django, Node.js·NestJS, Laravel, .NET), REST API 설계·개발, 외부 API 연동, "
          "WebSocket·gRPC·소켓 통신, Redis 캐시, 메시지 큐(Kafka·RabbitMQ)·비동기 처리, 인증·인가·보안(OAuth·JWT·시큐어 코딩·개인정보 보호), "
          "MSA·분산 시스템·대용량 트래픽·확장성 설계, 결제·주문 같은 서버 로직, '백엔드 개발'·'서버 개발' 경험"),
    ("D", "데이터베이스", "개발", "SQL, RDBMS(MySQL·PostgreSQL·Oracle), NoSQL, DB 설계·데이터 모델링, 쿼리 튜닝, 트랜잭션·인덱스, DBA, DB 마이그레이션, Elasticsearch 같은 검색 엔진"),
    ("E", "데이터 엔지니어링·분석", "개발", "데이터 파이프라인·ETL, Airflow, Spark·Databricks, 스트리밍, 배치·스케줄러, DW·Lakehouse, 크롤링·데이터 수집, "
          "데이터 분석·통계·시각화·대시보드, '데이터 엔지니어링' 경험"),
    ("O", "인프라·배포·운영", "개발", "AWS·GCP·Azure, Linux·Windows 서버, 네트워크, 가상화, IaC(Terraform), Docker·Kubernetes, CI/CD, 배포 자동화, "
          "모니터링·로그, 장애 대응·트러블슈팅, 성능 튜닝, 서비스 운영"),
    ("Q", "협업·코드 품질", "개발", "Git·형상관리, Jira·Confluence·Notion, 빌드 도구(Maven·Gradle), 애자일, PM·기술 리드, 설계 문서·화면 설계서, "
          "테스트 코드·QA, 코드 리뷰, 리팩토링·레거시 개선, 남이 짠 코드 분석, 디버깅"),
    ("F", "프론트엔드·앱", "개발", "React·Vue·Next.js, HTML/CSS·반응형, 관리자 페이지 화면, UI/UX·Figma, 모바일 앱(iOS·Android·Flutter·React Native)과 스토어 배포"),
    ("A", "AI 활용", "개발", "AI 코딩 도구(Cursor·Claude Code·Copilot)·바이브코딩·프롬프트 엔지니어링, LLM API 연동, RAG·벡터 검색, LangChain·MCP·에이전트 연동, MLOps"),
    ("M", "도메인 지식", "공통", "업종·업무 지식: 금융·증권·보험, 커머스·결제·물류, 의료·헬스케어, 제조, 공공·SI, ERP·SAP·MES, 광고·마케팅, 교육 등"),
    ("P", "소프트 스킬", "공통", "커뮤니케이션·협업, 문서 작성·발표, 문제 해결·논리적 사고, 학습·성장 태도, 주도성·책임감, 고객·현업 요구사항 정리"),
    ("G", "개발 일반", "애매", "영역을 전혀 알 수 없는 개발 경험만 적힌 줄(예: '개발 경험', '소프트웨어 개발 경력') — 그 줄이 나온 자리의 직무로 바꾼다"),
    ("X", "지원 조건", "조건", "레벨은 매기지 않는 조건: 학력·전공, 기술 없이 연차·신입·경력만, 자격증, 외국어, 근무 조건(병역·거주·출장·운전·입사일·보훈·장애), "
          "포트폴리오·논문·수상 같은 실적 제출"),
]
CODES = [c[0] for c in CATEGORIES]
NAME = {c[0]: c[1] for c in CATEGORIES}
JOB_CATEGORY = {"백엔드": "B", "데이터 엔지니어": "E"}   # 개발 일반(G) → 자리 직무의 카테고리

INSTRUCTIONS = """너는 백엔드·데이터 엔지니어 채용공고의 필수·우대 사항 한 줄마다, 그 줄이 요구하는 능력의 카테고리를 고른다.

카테고리:
""" + "\n".join(f"- {c}: {n} — {d}" for c, n, _, d in CATEGORIES) + """

규칙:
- 줄이 요구하는 것에 해당하는 카테고리를 모두 고른다. 보통 1~3개. 억지로 늘리지 않는다.
- 언어 이름이 적혀 있으면 L 도 고른다(예: 'Java·Spring Boot 개발' → L, B).
- 한 언어로만 쓰는 프레임워크·라이브러리만 적혀 있어도 그 언어를 쓰는 것이므로 L 을 고른다(예: 'React 개발' → F, L):
  Spring·JPA·MyBatis → Java, Django·FastAPI·Flask·Pandas → Python, React·Vue·Next.js·Node.js·NestJS → JavaScript/TypeScript,
  .NET → C#, Laravel → PHP, Flutter → Dart, iOS 네이티브 → Swift, Android 네이티브 → Kotlin/Java.
  Docker·AWS·Kubernetes·Git 처럼 언어와 상관없는 도구는 L 이 아니다. SQL 은 D 다.
- '백엔드 개발'·'서버 개발' 경험은 B, '풀스택 개발'은 B 와 F, '데이터 엔지니어링' 경험은 E 다.
- 연차가 붙어 있어도 기술이 적혀 있으면 그 기술의 카테고리다(예: 'Python 3년 이상' → L). 기술 없이 연차·경력·신입만 있으면 X.
- 자격증·학위·외국어 점수는 그 분야가 무엇이든 X 다(예: 'AWS 자격증 보유' → X).
- 업종·업무 경험은 M 이고, 기술과 함께 있으면 둘 다 고른다(예: '금융권 Java 개발' → L, M).
- AI 도구를 써서 개발하는 것과 LLM 기능을 서비스에 붙이는 것은 모두 A 다.
- 영역을 전혀 알 수 없는 개발 경험만 있으면 G.
입력의 줄마다 id 를 그대로 돌려준다. 모든 줄에 답한다."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "cats"],
        "properties": {"id": {"type": "integer"},
                       "cats": {"type": "array", "items": {"type": "string", "enum": CODES}}}}}},
}
PROMPT_VERSION = hashlib.sha256((INSTRUCTIONS + json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:12]


def load_texts(embed_model: str) -> tuple[Counter, dict[str, Counter]]:
    """서로 다른 원래 글 → 몇 줄에 나오나, 그 글이 나온 자리 직무별 줄 수."""
    path = os.path.join(HERE, "out", "embed", embed_model, "items.tsv")
    counts, jobs = Counter(), {}
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="	"):
            t = r["text"].strip()
            counts[t] += 1
            jobs.setdefault(t, Counter())[r.get("job") or ""] += 1
    return counts, jobs


def resolve(cats: list[str], jobs: Counter) -> list[str]:
    """개발 일반(G)을 그 글이 나온 자리 직무의 카테고리로 바꾼다(백엔드 → B, 데이터 엔지니어 → E, 둘 다 나오면 둘 다)."""
    if "G" not in cats:
        return cats
    to = [JOB_CATEGORY[j] for j in jobs if j in JOB_CATEGORY] or ["G"]
    return sorted(set([c for c in cats if c != "G"] + to), key=CODES.index)


def load_done(path: str) -> dict[str, list[str]]:
    done = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            r = json.loads(ln)
            if r["prompt"] == PROMPT_VERSION:
                done[r["text"]] = r["cats"]
    return done


def classify(client, model: str, effort: str, texts: list[str]) -> tuple[dict[str, list[str]], int, int]:
    """글 묶음 한 번 → {글: 카테고리}. 빠진 줄은 한 번 더 묻는다."""
    out, tin, tout = {}, 0, 0
    todo = list(texts)
    for _ in range(2):
        inp = "\n".join(f"{i}\t{t}" for i, t in enumerate(todo))
        resp = client.responses.create(
            model=model, instructions=INSTRUCTIONS, input=inp, max_output_tokens=16000,
            reasoning={"effort": effort},
            text={"format": {"type": "json_schema", "name": "categories", "schema": SCHEMA, "strict": True}})
        tin += resp.usage.input_tokens
        tout += resp.usage.output_tokens
        for it in json.loads(resp.output_text)["items"]:
            if 0 <= it["id"] < len(todo) and it["cats"]:
                out[todo[it["id"]]] = sorted(set(it["cats"]), key=CODES.index)
        todo = [t for t in todo if t not in out]
        if not todo:
            break
    return out, tin, tout


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>줄별 카테고리</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#ddd;--soft:#f3f3f3;--x:#999}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Malgun Gothic",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px}
h1{font-size:17px;margin:0 0 8px}
.cats{display:flex;flex-wrap:wrap;gap:6px}
.cats button{padding:3px 9px;border:1px solid #999;background:var(--bg);border-radius:12px;cursor:pointer;font:inherit;font-size:13px}
.cats button.on{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.cats button small{color:inherit;opacity:.7}
.sum{color:var(--mute);font-size:13px;margin-top:8px}
main{padding:8px 16px 40px;max-width:1000px}
.row{display:flex;gap:10px;padding:5px 0;border-bottom:1px solid var(--line);align-items:baseline}
.row .t{flex:1}
.row .n{color:var(--mute);font-size:12px;min-width:3em;text-align:right}
.tag{display:inline-block;font-size:12px;padding:0 7px;border-radius:10px;background:var(--soft);margin-left:4px;white-space:nowrap}
.tag.X,.tag.G{color:var(--x)}
</style></head><body>
<header><h1>줄별 카테고리 <small style="font-weight:400;color:var(--mute)">__MODEL__ · 지시문 __PROMPT__</small></h1>
<div class="cats" id="cats"></div><div class="sum" id="sum"></div></header>
<main id="list"></main>
<script>
const C = __CATS__, R = __ROWS__;   // R: [글, 줄 수, [코드…], [원래 답 — 개발 일반을 자리 직무로 바꾼 줄만]]
let pick = "", only = false;
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const name = Object.fromEntries(C.map(c => [c[0], c[1]]));
function render() {
  const rows = R.filter(r => !pick || (pick === "*" ? r[2].length > 1 : pick === "~" ? r[3].length > 0 : r[2].includes(pick)));
  document.getElementById("sum").textContent = `글 ${rows.length}개 / ${R.length}개 · 줄 ${rows.reduce((a, r) => a + r[1], 0)}개`;
  document.getElementById("list").innerHTML = rows.map(r =>
    `<div class="row"><span class="t">${esc(r[0])}</span><span>${r[2].map(c => `<span class="tag ${c}">${name[c]}</span>`).join("")}${r[3].length ? '<span class="tag X" title="LLM 은 개발 일반으로 답함 → 자리 직무로 바꿈">개발 일반→직무</span>' : ""}</span><span class="n">${r[1]}줄</span></div>`).join("");
}
const box = document.getElementById("cats");
const cnt = c => R.filter(r => r[2].includes(c)).length;
[["", "전체", R.length], ["*", "여러 개 붙은 줄", R.filter(r => r[2].length > 1).length], ["~", "개발 일반→직무", R.filter(r => r[3].length).length], ...C.map(c => [c[0], c[1], cnt(c[0])])].forEach(([k, n, m]) => {
  const b = document.createElement("button"); b.innerHTML = `${esc(n)} <small>${m}</small>`; if (k === pick) b.classList.add("on");
  b.onclick = () => { pick = k; [...box.children].forEach(x => x.classList.toggle("on", x === b)); render(); }; box.appendChild(b); });
render();
</script></body></html>
"""


def write_page(path: str, model: str, rows: list) -> None:
    page = (PAGE.replace("__MODEL__", html.escape(model)).replace("__PROMPT__", PROMPT_VERSION)
                .replace("__CATS__", json.dumps([[c, n] for c, n, _, _ in CATEGORIES], ensure_ascii=False))
                .replace("__ROWS__", json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--embed-model", default="text-embedding-3-large")
    ap.add_argument("--sample", type=int, default=0, help="시험: 줄 N개만(나오는 횟수만큼 뽑힐 확률이 큼)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    counts, text_jobs = load_texts(args.embed_model)
    d = os.path.join(HERE, "out", "classify", args.model)
    os.makedirs(d, exist_ok=True)
    lp = os.path.join(d, "labels.jsonl")
    done = load_done(lp)

    if args.sample:
        lines = [t for t, n in counts.items() for _ in range(n)]
        random.Random(12).shuffle(lines)
        targets = list(dict.fromkeys(lines))[:args.sample]   # 자주 나오는 글이 더 잘 뽑힌다
    else:
        targets = list(counts)
    todo = [t for t in targets if t not in done]
    print(f"대상 글 {len(targets)}개 (이미 붙인 것 {len(targets) - len(todo)}개, 새로 {len(todo)}개) · 지시문 {PROMPT_VERSION}", flush=True)

    tin = tout = 0
    if todo:
        from openai import OpenAI
        client = OpenAI(max_retries=4, timeout=300)
        batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
        t0 = time.perf_counter()
        with ThreadPoolExecutor(args.workers) as pool, open(lp, "a", encoding="utf-8") as f:
            futs = [pool.submit(classify, client, args.model, args.effort, b) for b in batches]
            for k, fu in enumerate(as_completed(futs), 1):
                got, i, o = fu.result()
                tin += i
                tout += o
                for t, cats in got.items():
                    done[t] = cats
                    f.write(json.dumps({"text": t, "cats": cats, "prompt": PROMPT_VERSION}, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {k}/{len(batches)}  {time.perf_counter() - t0:.0f}s", flush=True)
    pin, pout = PRICES.get(args.model, (0, 0))
    usd = tin / 1e6 * pin + tout / 1e6 * pout
    missing = [t for t in targets if t not in done]

    # 화면·집계는 개발 일반(G)을 자리 직무로 바꾼 뒤의 카테고리. 바꾼 줄은 네 번째 칸에 원래 답(G 포함)을 남긴다.
    rows = sorted(([t, counts[t], resolve(done[t], text_jobs[t]), done[t] if "G" in done[t] else []] for t in targets if t in done),
                  key=lambda r: -r[1])
    page = os.path.join(d, "sample.html" if args.sample else "labels.html")
    write_page(page, args.model, rows)

    total = sum(r[1] for r in rows)
    by, by_text = Counter(), Counter()
    for t, n, cats, _ in rows:
        for c in cats:
            by[c] += n
            by_text[c] += 1
    print(f"토큰 입력 {tin} 출력 {tout}  약 ${usd:.4f}  · 답 없는 글 {len(missing)}개")
    print("카테고리별 글 수 · 줄 비율(한 줄이 여러 곳에 들어가 합이 100%를 넘음):")
    for c in CODES:
        print(f"  {NAME[c]:<14} 글 {by_text[c]:>5}  줄 {by[c] / total * 100:5.1f}%")
    print(f"  여러 개 붙은 글 {sum(len(r[2]) > 1 for r in rows)}개 / {len(rows)}개 · 개발 일반을 자리 직무로 바꾼 글 {sum(bool(r[3]) for r in rows)}개")
    print(f"보기: {page}")


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
