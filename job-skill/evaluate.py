"""
4단계 평가 — truth.tsv 를 사용자가 검수한 뒤에만 실행한다.

  1) 스킬 재현율: 정답(필수 ∪ 우대) 중 뽑은 글자에 들어 있는 비율. 대소문자·공백 무시(지시서 기준).
     예외: 영문·숫자 3자 이하 스킬(C, C#, SQL, Git, DNS, LLM …)은 단순 포함으로는 의미가 없어서
     (C 는 아무 글자에나, SQL 은 PostgreSQL 에, DNS 는 DDNS 에, LLM 은 vLLM 에 들어 있다)
     앞뒤가 영문·숫자가 아닐 때만 인정한다.
  2) 지어낸 내용 후보: 뽑은 글자에 있는 기술명(어휘집) 중 그 공고 정답 3개 열 어디에도 없는 것
     -> eval/hallucination_candidates.tsv. 이미지와 대조해 verdict 열을 채운 eval/hallucination_review.tsv 가
     있으면 그 판정(지어냄/이미지에 있음)으로 센다. LLM 후보는 A 후보 출력 어디에도 없는 영문 토큰도 따로 뽑는다.
  3) 필수·우대 보존: eval/structure_review.tsv (candidate, rec_idx, preserved=예/아니오, 근거) 를 읽는다.
     판정 보조용으로 각 출력의 자격요건~우대사항 구간을 eval/structure_segments/ 에 뽑아 둔다.
  4) 처리 시간: out/<후보>/_timing.tsv 의 이미지당 평균.
  5) 비용: LLM 은 _calls.jsonl 토큰 x 단가, 로컬 OCR 은 0.

실행: py -3.12 evaluate.py      -> eval/*.tsv, result.md
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import defaultdict

from common import HERE, OUT_DIR, images_by_posting, load_targets

EVAL_DIR = os.path.join(HERE, "eval")
# 단가(USD / 1M 토큰). 출처: developers.openai.com/api/docs/pricing, 2026-10-02 확인.
PRICES = {"gpt-5.6-terra": (2.00, 12.00), "gpt-5.6-luna": (0.20, 1.20), "gpt-5.6-sol": (4.00, 20.00)}

# 지어낸 내용 탐지용 일반 기술명(정답에 없는 이름이 출력에 나타나는지 보려는 것)
COMMON_TECH = """Java Kotlin Python Django Flask FastAPI Node.js Express NestJS React Vue Angular Svelte Next.js Nuxt
TypeScript JavaScript Go Golang Rust C C++ C# .NET ASP.NET PHP Laravel Ruby Rails Swift Objective-C Scala Dart Flutter
Android iOS Spring Spring Boot Spring Security Spring Cloud MySQL MariaDB PostgreSQL Oracle MS-SQL SQL Server MongoDB
Redis Elasticsearch Kafka RabbitMQ Docker Kubernetes K8s AWS GCP Azure NCP Terraform Ansible Jenkins GitHub GitLab
GitHub Actions ArgoCD Git SVN Linux Ubuntu CentOS Nginx Apache Tomcat JPA Hibernate MyBatis QueryDSL GraphQL gRPC
REST API RESTful MSA CI/CD PyTorch TensorFlow Keras scikit-learn Pandas NumPy Spark Hadoop Airflow LangChain LangGraph
LlamaIndex OpenAI GPT ChatGPT LLM RAG vLLM SGLang Hugging Face HuggingFace Transformer MLOps Kubeflow MLflow Tableau
Power BI Databricks Snowflake BigQuery Figma Jira Confluence Supabase Vercel Firebase Datadog Grafana Prometheus Sentry
ELK Kibana Logstash Deeplearning4j Eclipse IntelliJ VS Code Toad SSMS WebLogic JEUS WebtoB Lena Cursor Claude Gemini
Copilot Distillation Quantization Pruning LoRA Unity Catalog Lakehouse Cloudflare Lambda EKS ECS EC2 S3 DynamoDB
Webpack Vite Jest Storybook Prometheus Loki Superset Iceberg Athena Tekton CloudFormation NATS DNS DDNS P2P TCP UDP
SQL NoSQL RDBMS Windows Unix Shell Bash""".split()
MULTIWORD = ["Spring Boot", "Spring Security", "Spring Cloud", "SQL Server", "GitHub Actions", "REST API",
             "Hugging Face", "Power BI", "VS Code", "Unity Catalog", "SQL Warehouse", "Claude Code", "API Gateway",
             "Spring Framework", "React Native", "Serverless Framework", "Tanstack Query", "Apache Airflow"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- 매칭

def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _is_ascii(s: str) -> bool:
    return all(ord(ch) < 128 for ch in s)


def _bounded_regex(term: str) -> re.Pattern:
    """앞뒤가 영문·숫자가 아닐 때만 맞는 정규식. 용어 안의 공백은 있어도 없어도 된다."""
    body = r"\s*".join(re.escape(ch) for ch in re.sub(r"\s+", "", term.lower()))
    tail = r"(?![a-z0-9+#])" if term[-1:].isalnum() else r"(?![a-z0-9])"
    return re.compile(r"(?<![a-z0-9])" + body + tail)


def present_recall(skill: str, text: str) -> bool:
    """재현율용(지시서 기준 + 짧은 영문 예외)."""
    if _is_ascii(skill) and len(_alnum(skill)) <= 3:
        return bool(_bounded_regex(skill).search(text.lower()))
    return re.sub(r"\s+", "", skill.lower()) in re.sub(r"\s+", "", text.lower())


def present_strict(term: str, text: str) -> bool:
    """지어낸 내용 탐지용: 영문 용어는 모두 경계를 본다(Java 가 JavaScript 안에서 맞지 않게)."""
    if _is_ascii(term):
        return bool(_bounded_regex(term).search(text.lower()))
    return re.sub(r"\s+", "", term.lower()) in re.sub(r"\s+", "", text.lower())


def find_context(term: str, text: str, width: int = 40) -> str:
    low = text.lower()
    if _is_ascii(term):
        m = _bounded_regex(term).search(low)
        i, j = (m.start(), m.end()) if m else (0, 0)
    else:
        i = low.find(term.lower())
        j = i + len(term)
    return text[max(0, i - width):j + width].replace("\n", " / ").replace("\t", " ")


# ---------------------------------------------------------------- 입력

def split_list(cell: str) -> list[str]:
    return [s.strip() for s in (cell or "").split(",") if s.strip()]


def load_truth() -> dict[str, dict[str, list[str]]]:
    with open(os.path.join(HERE, "truth.tsv"), encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    out = {}
    for r in rows[1:]:
        r += [""] * (4 - len(r))
        out[r[0].strip()] = {"req": split_list(r[1]), "pref": split_list(r[2]), "other": split_list(r[3])}
    return out


def candidates() -> list[str]:
    order = ["tesseract", "easyocr", "paddleocr"]
    found = [d for d in os.listdir(OUT_DIR) if os.path.isdir(os.path.join(OUT_DIR, d)) and not d.startswith("_")]
    return [c for c in order if c in found] + sorted(c for c in found if c not in order)


def read_out(cand: str, rid: str) -> str:
    p = os.path.join(OUT_DIR, cand, f"{rid}.txt")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def read_tsv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: str, rows: list[dict], fields: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- 지표

def recall_rows(truth, cands) -> list[dict]:
    rows = []
    for rid, t in truth.items():
        skills = list(dict.fromkeys(t["req"] + t["pref"]))
        for c in cands:
            text = read_out(c, rid)
            for s in skills:
                kind = "필수+우대" if s in t["req"] and s in t["pref"] else ("필수" if s in t["req"] else "우대")
                rows.append({"candidate": c, "rec_idx": rid, "skill": s, "kind": kind,
                             "found": int(present_recall(s, text))})
    return rows


def lexicon(truth) -> list[str]:
    terms = set(COMMON_TECH) | set(MULTIWORD)
    for t in truth.values():
        terms |= set(t["req"]) | set(t["pref"]) | set(t["other"])
    return sorted(terms, key=lambda s: (-len(s), s.lower()))


def hallucination_candidates(truth, cands) -> list[dict]:
    lex = lexicon(truth)
    rows = []
    for rid, t in truth.items():
        image_terms = ", ".join(t["req"] + t["pref"] + t["other"])
        for c in cands:
            text = read_out(c, rid)
            for term in lex:
                if present_strict(term, text) and not present_strict(term, image_terms):
                    rows.append({"candidate": c, "rec_idx": rid, "term": term, "source": "어휘집",
                                 "context": find_context(term, text)})
    # LLM: A 후보 출력 어디에도 없고 정답에도 없는 영문 토큰(교정·창작 의심)
    a_cands = [c for c in cands if not c.startswith("llm_")]
    tok = re.compile(r"[A-Za-z][A-Za-z0-9.+#/-]*[A-Za-z0-9+#]|[A-Za-z]")
    for c in (c for c in cands if c.startswith("llm_")):
        for rid, t in truth.items():
            text = read_out(c, rid)
            a_text = " ".join(read_out(a, rid) for a in a_cands).lower()
            image_terms = ", ".join(t["req"] + t["pref"] + t["other"]).lower()
            seen = set()
            for m in tok.finditer(text):
                w = m.group(0)
                if len(_alnum(w)) < 3 or w.lower() in seen:
                    continue
                seen.add(w.lower())
                if w.lower() not in a_text and w.lower() not in image_terms:
                    rows.append({"candidate": c, "rec_idx": rid, "term": w, "source": "LLM에만 있는 영문",
                                 "context": find_context(w, text)})
    return rows


HEADER_HINT = re.compile(r"(자격|필수|요건|우대|Requirement|Preferred|함께\s*하고\s*싶|더\s*좋아요|더욱\s*좋아요|알고\s*계시면)", re.I)


def structure_segments(cands) -> None:
    """판정 보조: 출력에서 자격요건/우대 관련 머리말이 처음 나오는 줄부터 60줄을 뽑는다."""
    d = os.path.join(EVAL_DIR, "structure_segments")
    os.makedirs(d, exist_ok=True)
    for rid in images_by_posting():
        with open(os.path.join(d, f"{rid}.txt"), "w", encoding="utf-8") as f:
            for c in cands:
                lines = read_out(c, rid).splitlines()
                idx = next((i for i, l in enumerate(lines) if HEADER_HINT.search(l)), 0)
                f.write(f"===== {c} (줄 {idx + 1}~)\n" + "\n".join(lines[idx:idx + 60]) + "\n\n")


def timing(cand: str) -> tuple[float, float, int]:
    rows = read_tsv(os.path.join(OUT_DIR, cand, "_timing.tsv"))
    secs = [float(r["seconds"]) for r in rows]
    return (sum(secs) / len(secs) if secs else 0.0), sum(secs), len(secs)


def llm_cost(cand: str) -> dict[str, dict]:
    model = cand[len("llm_"):]
    pin, pout = PRICES.get(model, (0.0, 0.0))
    per = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "usd": 0.0})
    path = os.path.join(OUT_DIR, cand, "_calls.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            c = json.loads(line)
            p = per[c["rec_idx"]]
            p["calls"] += 1
            p["in"] += int(c["input_tokens"])
            p["out"] += int(c["output_tokens"])
            p["usd"] += int(c["input_tokens"]) / 1e6 * pin + int(c["output_tokens"]) / 1e6 * pout
    return per


# ---------------------------------------------------------------- 결과

def pct(a: int, b: int) -> str:
    return f"{a / b * 100:.1f}% ({a}/{b})" if b else "-"


def main() -> None:
    truth = load_truth()
    cands = candidates()
    titles = {t["rec_idx"]: t["company"] for t in load_targets()}
    os.makedirs(EVAL_DIR, exist_ok=True)

    rec = recall_rows(truth, cands)
    write_tsv(os.path.join(EVAL_DIR, "recall_detail.tsv"), rec, ["candidate", "rec_idx", "skill", "kind", "found"])

    hal = hallucination_candidates(truth, cands)
    write_tsv(os.path.join(EVAL_DIR, "hallucination_candidates.tsv"), hal,
              ["candidate", "rec_idx", "term", "source", "context"])
    review = read_tsv(os.path.join(EVAL_DIR, "hallucination_review.tsv"))
    fabricated = defaultdict(list)
    for r in review:
        if r.get("verdict", "").strip() in ("지어냄", "고쳐 씀"):
            fabricated[(r["candidate"], r["rec_idx"])].append(f"{r['term']}({r['verdict'].strip()})")

    structure_segments(cands)
    struct = {(r["candidate"], r["rec_idx"]): r for r in read_tsv(os.path.join(EVAL_DIR, "structure_review.tsv"))}

    lines = ["# OCR 비교 테스트 결과", ""]
    # 후보별 표
    lines += ["## 후보별", "",
              "| 후보 | 스킬 재현율 | 필수 재현율 | 우대 재현율 | 지어낸 내용 | 필수·우대 보존(예) | 이미지당 평균 시간 | 공고 1건당 비용 |",
              "|---|---|---|---|---|---|---|---|"]
    rids = list(truth)
    for c in cands:
        mine = [r for r in rec if r["candidate"] == c]
        f_all = sum(r["found"] for r in mine)
        req = [r for r in mine if r["kind"] in ("필수", "필수+우대")]
        pref = [r for r in mine if r["kind"] in ("우대", "필수+우대")]
        n_fab = sum(len(fabricated[(c, rid)]) for rid in rids)
        n_yes = sum(1 for rid in rids if struct.get((c, rid), {}).get("preserved") == "예")
        n_judged = sum(1 for rid in rids if (c, rid) in struct)
        avg, _total, n_img = timing(c)
        if c.startswith("llm_"):
            per = llm_cost(c)
            usd = sum(p["usd"] for p in per.values()) / max(1, len(per))
            calls = sum(p["calls"] for p in per.values()) / max(1, len(per))
            tin = sum(p["in"] for p in per.values()) / max(1, len(per))
            tout = sum(p["out"] for p in per.values()) / max(1, len(per))
            cost = f"${usd:.4f} (호출 {calls:.1f}회, 입력 {tin:,.0f}·출력 {tout:,.0f} 토큰)"
        else:
            cost = "0 (로컬 CPU)"
        lines.append(f"| {c} | {pct(f_all, len(mine))} | {pct(sum(r['found'] for r in req), len(req))} | "
                     f"{pct(sum(r['found'] for r in pref), len(pref))} | "
                     f"{n_fab if review else '판정 전'} | {f'{n_yes}/{n_judged}' if n_judged else '판정 전'} | "
                     f"{avg:.1f}초 ({n_img}장) | {cost} |")
    # 공고별 표
    lines += ["", "## 공고별 (스킬 재현율 · 필수·우대 보존)", "",
              "| rec_idx | 회사 | 정답 스킬 수 | " + " | ".join(cands) + " |",
              "|---|---|---|" + "---|" * len(cands)]
    for rid in rids:
        n = len(set(truth[rid]["req"] + truth[rid]["pref"]))
        cells = []
        for c in cands:
            got = sum(r["found"] for r in rec if r["candidate"] == c and r["rec_idx"] == rid)
            s = struct.get((c, rid), {}).get("preserved", "?")
            cells.append(f"{got}/{n} · {s}")
        lines.append(f"| {rid} | {titles.get(rid, '')} | {n} | " + " | ".join(cells) + " |")
    # 놓친 스킬
    lines += ["", "## 놓친 정답 스킬", ""]
    for c in cands:
        miss = [f"{r['rec_idx']}:{r['skill']}" for r in rec if r["candidate"] == c and not r["found"]]
        lines.append(f"- **{c}** ({len(miss)}개): " + (", ".join(miss) if miss else "없음"))
    if review:
        lines += ["", "## 지어낸 내용 (이미지와 대조해 확인한 것)", ""]
        for c in cands:
            items = [f"{rid}:{x}" for rid in rids for x in fabricated[(c, rid)]]
            lines.append(f"- **{c}** ({len(items)}개): " + (", ".join(items) if items else "없음"))
    notes = os.path.join(HERE, "result_notes.md")
    if os.path.exists(notes):
        lines += ["", open(notes, encoding="utf-8").read().rstrip()]
    with open(os.path.join(HERE, "result.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:4 + len(cands) + 2]))
    print(f"\n지어낸 내용 후보 {len(hal)}건 -> eval/hallucination_candidates.tsv (판정 후 hallucination_review.tsv)")


if __name__ == "__main__":
    main()
