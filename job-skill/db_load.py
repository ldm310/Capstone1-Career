"""
DB 저장(Load): 표 만들기 · 표준화 사전 동기화 · 공고와 추출 결과 넣기 (PostgreSQL).

연결은 DATABASE_URL 로 한다(코드에 비밀번호를 넣지 않는다). 환경변수가 없으면 이 폴더의 .env 에서 읽는다.
  DB 띄우기: docker compose up -d   (docker-compose.yml, 비밀번호는 .env — .env.example 참고)

실행:
  py -3.12 db_load.py init                                  # 표 만들기(db/schema.sql) + 사전 채우기(db/seed_dictionary.sql). 이미 있으면 건너뜀
  py -3.12 db_load.py export-dict                            # DB 사전 -> db/seed_dictionary.sql (사전을 고친 뒤 내려받아 커밋)
  py -3.12 db_load.py sync-dict                              # capabilities.json -> 사전 표 (한 방향)
  $env:OCR_DATA_DIR = "sample3"
  py -3.12 db_load.py load --run gpt-5.6-luna-ex-chk         # 공고·이미지 + out/extract/<run>/ 의 추출 결과

여러 번 돌려도 겹치지 않는다.
  - 공고는 (사이트, 사이트 공고번호)로 찾아 있으면 고친다.
  - 추출 결과는 (공고, 모델, 프롬프트 버전, 사전 버전, 입력 해시)가 같으면 이미 넣은 것으로 보고 건너뛴다.
  - 사전은 이름으로 찾아 고치고, JSON 에서 빠진 능력·기술은 지우지 않고 사용 여부를 false 로 둔다.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone

import psycopg
from psycopg.types.json import Jsonb

from common import IMG_DIR, OUT_DIR, PAGE_DIR, load_targets
from extract_skills import CATS, PRICES, llm_input, review_reasons, sha256
from fetch_images import RELAY, image_urls
from html_text import BODY, html_text
from sample_random import min_years

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_SQL = os.path.join(HERE, "db", "schema.sql")
SEED_SQL = os.path.join(HERE, "db", "seed_dictionary.sql")   # 빈 DB 를 채우는 사전(export-dict 로 DB 에서 내려받음)
DICT_JSON = os.path.join(HERE, "capabilities.json")
EX = os.path.join(OUT_DIR, "extract")
SAVE_TRIES = 3   # 공고 하나 저장을 일시 오류(연결 끊김·교착)일 때 몇 번까지 할지
RETRY_WAIT = 2   # 다시 하기 전 기다림(초) × 몇 번째
CAT_KO = {"required": "필수", "preferred": "우대", "duties": "업무", "other": "기타"}
OTHER = "기타"  # 사전에 맞는 능력이 없을 때 가리키는 능력
SCHEMA = "public"  # 이 파이프라인의 표는 모두 기본 스키마 public 에 있다(BE 표와 같은 곳)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


RDS_USER = RDS_DB = "career"


def _env_file() -> dict[str, str]:
    """이 폴더의 .env (저장소에 올리지 않는다)."""
    path = os.path.join(HERE, ".env")
    out = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            k, _, v = ln.strip().partition("=")
            if k and v:
                out[k] = v
    return out


def database_url() -> str | None:
    """파이프라인이 쓰는 DB (AWS 브랜치).
    1) 환경변수 DATABASE_URL 을 값과 함께 직접 줬으면 그것(시험의 임시 DB 등)
    2) RDS_HOST·RDS_PASSWORD(환경변수 또는 .env)가 있으면 AWS RDS — 암호화 접속(sslmode=require)
    3) 그것도 없으면 .env 의 DATABASE_URL(로컬 Docker career-db)
    Airflow 컨테이너는 DATABASE_URL 을 빈 값으로 덮어 2) 로 간다."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env = _env_file()
    host = os.environ.get("RDS_HOST") or env.get("RDS_HOST")
    pw = os.environ.get("RDS_PASSWORD") or env.get("RDS_PASSWORD")
    if host and pw:
        from urllib.parse import quote
        return f"postgresql://{RDS_USER}:{quote(pw, safe='')}@{host}:5432/{RDS_DB}?sslmode=require"
    return env.get("DATABASE_URL")


def local_database_url() -> str | None:
    """시험용 DB(로컬 Docker career-db): TEST_DATABASE_URL, 없으면 .env 의 DATABASE_URL.
    시험은 임시 DB 를 만들었다 지우므로 RDS 에서 하지 않는다."""
    return os.environ.get("TEST_DATABASE_URL") or _env_file().get("DATABASE_URL")


def connect(autocommit: bool = False) -> psycopg.Connection:
    url = database_url()
    if not url:
        sys.exit("DATABASE_URL 이 없습니다. .env.example 을 .env 로 복사해 채우거나 환경변수로 설정하세요.")
    # 스키마 이름을 붙이지 않은 표 이름은 public 에서 찾는다
    return psycopg.connect(url, autocommit=autocommit, options=f"-c search_path={SCHEMA}")


# ---------------------------------------------------------------- 값 다듬기

def content_hash(page: str, rid: str) -> str:
    """원본 해시: 화면에 보이는 글(띄어쓰기·줄바꿈 제거) + 본문 이미지 주소.
    사람인 본문 HTML 에는 요청마다 색 값이 무작위인 빈 <font> 태그가 들어가 HTML 그대로는 매번 달라진다."""
    text = re.sub(r"\s+", "", html_text(page))
    return sha256(text + "\n" + "\n".join(image_urls(page, RELAY.format(id=rid))))


def parse_years(s: str) -> tuple[int | None, int | None]:
    """연수 글 -> (최소, 최대). 예: '3년 이상' (3, None) · '5~7년' (5, 7) · '1년 이상 ~ 3년 이하' (1, 3) · '9년 미만' (None, 8)."""
    t = re.sub(r"\s+", "", s or "")
    lo = re.search(r"(\d+)년(이상|초과)", t)
    hi = re.search(r"(\d+)년(이하|미만)", t)
    if lo or hi:
        a = None if not lo else int(lo.group(1)) + (1 if lo.group(2) == "초과" else 0)
        b = None if not hi else int(hi.group(1)) - (1 if hi.group(2) == "미만" else 0)
    elif m := re.search(r"(\d+)~(\d+)년", t):
        a, b = int(m.group(1)), int(m.group(2))
    elif m := re.search(r"(\d+)년", t):
        a, b = int(m.group(1)), None
    else:
        return None, None
    clamp = lambda v: None if v is None else max(0, min(50, v))
    a, b = clamp(a), clamp(b)
    if a is not None and b is not None and a > b:
        b = a
    return a, b


def employment_type(career: str) -> str | None:
    """사람인 경력 조건 '신입 · 경력 · 정규직 외' -> '정규직 외' (경력 부분을 뺀 나머지)."""
    parts = [p.strip() for p in (career or "").split("·")]
    rest = [p for p in parts if p and not re.search(r"신입|경력|년|무관", p)]
    return " · ".join(rest) or None


# ---------------------------------------------------------------- init

def cmd_init() -> None:
    with connect(autocommit=True) as conn:
        if conn.execute("SELECT to_regclass(%s)", (f"{SCHEMA}.posting",)).fetchone()[0]:
            print("표가 이미 있습니다. 건너뜁니다.")
            return
        conn.execute(open(SCHEMA_SQL, encoding="utf-8").read())
        conn.execute(open(SEED_SQL, encoding="utf-8").read())
        n = conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname = %s", (SCHEMA,)).fetchone()[0]
        print(f"스키마 {SCHEMA} 에 표 {n}개를 만들고 사전을 채웠습니다.")


# ---------------------------------------------------------------- sync-dict

def cmd_sync_dict() -> None:
    d = json.load(open(DICT_JSON, encoding="utf-8"))
    version = (d.get("version") or "").split()[0] or "unknown"
    caps = dict(d["capabilities"])
    caps.setdefault(OTHER, {})
    techs = d["techs"]
    bad = sorted({c for t in techs.values() for c in t.get("caps", []) if c not in caps})
    if bad:
        sys.exit(f"기술이 가리키는 능력이 사전에 없습니다: {bad}")

    with connect() as conn, conn.transaction():
        for name, v in caps.items():
            conn.execute("""INSERT INTO capability (name, group_name, aliases, is_active) VALUES (%s, %s, %s, true)
                            ON CONFLICT (name) DO UPDATE
                            SET group_name = EXCLUDED.group_name, aliases = EXCLUDED.aliases, is_active = true""",
                         (name, v.get("group"), v.get("aliases", [])))
        for name, v in techs.items():
            conn.execute("""INSERT INTO tech (name, aliases, is_active) VALUES (%s, %s, true)
                            ON CONFLICT (name) DO UPDATE SET aliases = EXCLUDED.aliases, is_active = true""",
                         (name, v.get("aliases", [])))
        cap_id = dict(conn.execute("SELECT name, id FROM capability").fetchall())
        tech_id = dict(conn.execute("SELECT name, id FROM tech").fetchall())
        # 상위 (관계형 DB -> 데이터베이스, EC2 -> AWS)
        for name, v in caps.items():
            conn.execute("UPDATE capability SET parent_id = %s WHERE id = %s", (cap_id.get(v.get("parent")), cap_id[name]))
        for name, v in techs.items():
            conn.execute("UPDATE tech SET parent_id = %s WHERE id = %s", (tech_id.get(v.get("parent")), tech_id[name]))
        # 기술-능력 연결은 통째로 다시 만든다(다른 표가 가리키지 않는다)
        conn.execute("DELETE FROM tech_capability")
        links = [(tech_id[t], cap_id[c]) for t, v in techs.items() for c in v.get("caps", [])]
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO tech_capability (tech_id, capability_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", links)
        # JSON 에서 빠진 것은 지우지 않고 사용 안 함
        off_c = conn.execute("UPDATE capability SET is_active = false WHERE is_active AND NOT (name = ANY(%s))",
                             (list(caps),)).rowcount
        off_t = conn.execute("UPDATE tech SET is_active = false WHERE is_active AND NOT (name = ANY(%s))",
                             (list(techs),)).rowcount
        conn.execute("""INSERT INTO dictionary_version (version) VALUES (%s)
                        ON CONFLICT (version) DO UPDATE SET synced_at = now()""", (version,))
    print(f"사전 {version}: 능력 {len(caps)}개, 기술 {len(techs)}개, 기술-능력 {len(links)}개 "
          f"(사용 안 함으로 바꿈: 능력 {off_c}, 기술 {off_t})")


# ---------------------------------------------------------------- export-dict

KINDS = ("LLM 모델", "기술 아님", "일반 낱말")   # exclude_word.kind (내보내는 순서)


def _sql(v) -> str:
    """SQL 값 글자: None -> NULL, bool, 글자 목록 -> ARRAY[...]::text[], 글자 -> '...'."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "ARRAY[" + ", ".join(_sql(x) for x in v) + "]::text[]" if v else "'{}'::text[]"
    return "'" + str(v).replace("'", "''") + "'"


def _values(rows: list[tuple], indent: str) -> str:
    return f",\n{indent}".join("(" + ", ".join(_sql(v) for v in r) + ")" for r in rows)


def export_dictionary(conn) -> str:
    """사전 4개 표 -> 빈 DB 를 채우는 SQL(사전이 이미 있으면 아무것도 안 함). 사용 안 함 줄도 내보낸다.
    능력·기술은 id 순(LLM 지시문의 능력 줄 순서·예시 기술 순서가 그대로 이어짐), 정렬은 파이썬에서 해서 DB 마다 같은 글이 나온다."""
    caps = conn.execute("SELECT id, name, group_name, aliases, is_active, parent_id FROM capability ORDER BY id").fetchall()
    techs = conn.execute("SELECT id, name, aliases, is_active, parent_id FROM tech ORDER BY id").fetchall()
    cap_name = {r[0]: r[1] for r in caps}
    tech_name = {r[0]: r[1] for r in techs}
    links = sorted(conn.execute("SELECT tech_id, capability_id, is_primary FROM tech_capability").fetchall(),
                   key=lambda r: (r[0], not r[2], r[1]))
    words = sorted(conn.execute("SELECT kind, word FROM exclude_word").fetchall(), key=lambda r: (KINDS.index(r[0]), r[1]))
    i = " " * 12
    parts = [
        "-- 표준화 사전 시드: 사전이 비어 있는 DB(테스트·CI·새 DB)만 채운다. 이미 사전이 있으면 아무것도 하지 않는다.",
        "-- 사전의 원본은 DB 다. 이 파일은 고치지 말고 'py -3.12 db_load.py export-dict' 로 DB 에서 다시 내려받는다.",
        "BEGIN;",
        "SET LOCAL search_path TO public;",
        "DO $seed$",
        "BEGIN",
        "    IF EXISTS (SELECT 1 FROM capability) THEN",
        "        RETURN;",
        "    END IF;",
    ]
    if caps:
        parts += ["    INSERT INTO capability (name, group_name, aliases, is_active) VALUES",
                  i + _values([(r[1], r[2], r[3], r[4]) for r in caps], i) + ";"]
    if techs:
        parts += ["    INSERT INTO tech (name, aliases, is_active) VALUES",
                  i + _values([(r[1], r[2], r[3]) for r in techs], i) + ";"]
    for table, rows, names in (("capability", caps, cap_name), ("tech", techs, tech_name)):
        parents = [(r[1], names[r[-1]]) for r in rows if r[-1] is not None]
        if parents:
            parts += [f"    UPDATE {table} x SET parent_id = p.id FROM (VALUES",
                      i + _values(parents, i),
                      f"        ) AS v (name, parent), {table} p",
                      "    WHERE x.name = v.name AND p.name = v.parent;"]
    if links:
        parts += ["    INSERT INTO tech_capability (tech_id, capability_id, is_primary)",
                  "    SELECT t.id, c.id, v.is_primary FROM (VALUES",
                  i + _values([(tech_name[t], cap_name[c], p) for t, c, p in links], i),
                  "        ) AS v (tech, cap, is_primary)",
                  "    JOIN tech t ON t.name = v.tech JOIN capability c ON c.name = v.cap;"]
    if words:
        parts += ["    INSERT INTO exclude_word (kind, word) VALUES",
                  i + _values(words, i) + ";"]
    parts += ["END $seed$;", "COMMIT;", ""]
    return "\n".join(parts)


def cmd_export_dict(out: str = SEED_SQL) -> None:
    """지금 접속한 DB(aws 브랜치면 RDS)의 사전을 out 에 내려받는다. 커밋하면 테스트·CI·새 DB 가 이 사전으로 채워진다."""
    with connect() as conn:
        text = export_dictionary(conn)
        n = [conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("capability", "tech", "tech_capability", "exclude_word")]
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"사전 -> {os.path.relpath(out, HERE)}: 능력 {n[0]}, 기술 {n[1]}, 연결 {n[2]}, 낱말 {n[3]}")


# ---------------------------------------------------------------- load

def image_rows() -> dict[str, list[dict]]:
    """images/manifest.tsv 에서 실제로 받은 이미지만 {rec_idx: [행]}."""
    path = os.path.join(IMG_DIR, "manifest.tsv")
    out: dict[str, list[dict]] = {}
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"):
        if r.get("file") and os.path.exists(os.path.join(IMG_DIR, r["file"])):
            out.setdefault(r["rec_idx"], []).append(r)
    return out


def kept_by_image() -> dict[str, bool]:
    """단락 나누기 결과(sections.json): 이미지에 '남기기' 단락이 하나라도 있으면 남김."""
    path = os.path.join(OUT_DIR, "page_filter", "sections.json")
    if not os.path.exists(path):
        return {}
    blob = json.load(open(path, encoding="utf-8"))
    out = {}
    for posts in blob.get("readers", {}).values():
        for p in posts:
            for im in p["images"]:
                out[im["file"]] = any(s["decision"] == "남기기" for s in im["sections"])
    return out


_DROP_TAGS = re.compile(r"<(script|style|iframe|noscript|object|embed)\b.*?(?:</\1\s*>|$)", re.S | re.I)
_ON_ATTR = re.compile(r"""\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_JS_URL = re.compile(r"""\b(href|src)\s*=\s*(["'])\s*javascript:[^"']*\2""", re.I)
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
_SRC_ATTR = re.compile(r"""\s(?:data-src|src)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_ATTR_VAL = re.compile(r"""\b(data-src|src)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)


def body_html(page: str, rid: str) -> str | None:
    """웹 상세 화면용 본문 HTML: 사람인 본문 칸(user_content)만, 표·문단·글과 이미지의 배치는 그대로 둔다.
    스크립트·스타일·iframe·on* 속성·javascript: 주소는 빼고, 이미지는 진짜 주소(늦게 불러오는 data-src 우선)를
    전체 주소로 바꿔 src 하나로 둔다. 본문 칸이 없으면 None. (팀 3명만 쓰는 화면이라 원문을 담기로 함 — 2026-10-29 사용자 결정)"""
    m = BODY.search(page)
    if not m:
        return None
    b = _DROP_TAGS.sub("", m.group(1))
    b = _ON_ATTR.sub("", b)
    b = _JS_URL.sub(r"\1=\2#\2", b)
    base = RELAY.format(id=rid)

    def fix(tag_m: re.Match) -> str:
        tag = tag_m.group(0)
        vals = {a.group(1).lower(): a.group(2) or a.group(3) or a.group(4) or "" for a in _ATTR_VAL.finditer(tag)}
        src = html.unescape(vals.get("data-src") or vals.get("src") or "").strip()
        if src and not src.startswith("data:"):
            src = urllib.parse.urljoin(base, src)
        tag = _SRC_ATTR.sub("", tag)
        return tag[:4] + f' src="{html.escape(src, quote=True)}"' + tag[4:]

    b = _IMG_TAG.sub(fix, b)
    b = re.sub(r"\s*</div>\s*$", "", b.strip())
    return b.strip() or None


def upsert_posting(conn, t: dict, update_raw: bool = True) -> int:
    """공고를 넣거나 고친다. 이미 있는 공고의 원본(body_html·raw_hash)은 update_raw 가 참일 때만 바꾼다
    (그 공고를 다시 추출하는 데 성공했을 때만 원본을 새것으로 — 실패하면 옛 원본을 두고 ②가 다시 잡는다).
    마지막 확인 시각도 같은 규칙: 실패한 공고는 옛 시각이 남는다.
    마지막 확인 시각에는 저장한 시각이 아니라 본문을 받은 시각(받아 둔 페이지 파일의 시각)을 넣는다 —
    받은 뒤 저장하기 전 사이(③ 은 몇 시간)에 고친 공고를 '이미 본 것'으로 놓치지 않게."""
    rid = t["rec_idx"]
    page_path = os.path.join(PAGE_DIR, f"{rid}.html")
    page = open(page_path, encoding="utf-8").read()
    fetched_at = datetime.fromtimestamp(os.path.getmtime(page_path), tz=timezone.utc)
    company_id = conn.execute("""INSERT INTO company (name) VALUES (%s)
                                 ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
                              (t["company"],)).fetchone()[0]
    return conn.execute(
        """INSERT INTO posting (company_id, site, site_posting_no, title, site_job_category, career_condition,
                                min_years, employment_type, kind, deadline, body_html, raw_hash, last_checked_at)
           VALUES (%(cid)s, '사람인', %(no)s, %(title)s, %(role)s, %(career)s, %(miny)s, %(emp)s, %(kind)s, %(deadline)s,
                   %(body)s, %(hash)s, %(fetched)s)
           ON CONFLICT (site, site_posting_no) DO UPDATE
           SET company_id = EXCLUDED.company_id, title = EXCLUDED.title, site_job_category = EXCLUDED.site_job_category,
               career_condition = EXCLUDED.career_condition, min_years = EXCLUDED.min_years,
               employment_type = EXCLUDED.employment_type, kind = EXCLUDED.kind,
               deadline = coalesce(EXCLUDED.deadline, posting.deadline),
               body_html = CASE WHEN %(update_raw)s THEN EXCLUDED.body_html ELSE posting.body_html END,
               raw_hash = CASE WHEN %(update_raw)s THEN EXCLUDED.raw_hash ELSE posting.raw_hash END,
               last_checked_at = CASE WHEN %(update_raw)s THEN EXCLUDED.last_checked_at ELSE posting.last_checked_at END
           RETURNING id""",
        {"cid": company_id, "no": rid, "title": t["title"], "role": t.get("role") or None,
         "career": t.get("career") or None, "miny": min_years(t.get("career", "")),
         "emp": employment_type(t.get("career", "")), "kind": t["kind"], "deadline": t.get("deadline") or None,
         "body": body_html(page, rid), "hash": content_hash(page, rid), "fetched": fetched_at,
         "update_raw": update_raw}).fetchone()[0]


def upsert_images(conn, posting_id: int, rows: list[dict], kept: dict[str, bool]) -> int:
    """받은 이미지의 순서·원본 주소·남김 여부. 노트북 파일 경로는 넣지 않는다(팀원·웹은 못 쓰는 값)."""
    for r in rows:
        conn.execute("""INSERT INTO posting_image (posting_id, seq, url, kept)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (posting_id, seq) DO UPDATE SET url = EXCLUDED.url, kept = EXCLUDED.kept""",
                     (posting_id, int(r["seq"]), r["url"], kept.get(r["file"])))
    return len(rows)


def migrate_body_html(conn, base: str | None = None) -> dict[str, int]:
    """한 번만(여러 번 돌려도 안전): 본문 HTML 칸을 만들고, 이미 저장된 공고는 노트북 원본 파일(raw_path)로 채운 뒤
    노트북에서만 쓸 수 있는 경로 칸(posting.raw_path, posting_image.file_path·ocr_path)을 뺀다.
    base 는 raw_path 의 기준 폴더(기본: 이 폴더). 파일이 없는 공고는 본문을 비워 둔다."""
    base = base or HERE

    def cols(table: str) -> set[str]:
        return {r[0] for r in conn.execute("""SELECT column_name FROM information_schema.columns
                                              WHERE table_schema = %s AND table_name = %s""", (SCHEMA, table))}

    res = {"채움": 0, "파일 없음": 0}
    with conn.transaction():
        conn.execute("ALTER TABLE posting ADD COLUMN IF NOT EXISTS body_html text")
        if "raw_path" in cols("posting"):
            for pid, no, path in conn.execute("SELECT id, site_posting_no, raw_path FROM posting WHERE body_html IS NULL").fetchall():
                full = os.path.join(base, path or "")
                if not path or not os.path.isfile(full):
                    res["파일 없음"] += 1
                    continue
                conn.execute("UPDATE posting SET body_html = %s WHERE id = %s",
                             (body_html(open(full, encoding="utf-8").read(), no), pid))
                res["채움"] += 1
            conn.execute("ALTER TABLE posting DROP COLUMN raw_path")
        conn.execute("ALTER TABLE posting_image DROP COLUMN IF EXISTS file_path, DROP COLUMN IF EXISTS ocr_path")
        conn.execute("""COMMENT ON COLUMN posting.body_html IS
                        '본문 HTML (사람인 본문 칸, 스크립트 등은 뺌, 이미지 주소는 전체 주소 — 웹 상세 화면용. 본문이 없으면 비움)'""")
    return res


def cmd_migrate_body_html() -> None:
    with connect() as conn:
        print(" · ".join(f"{k} {v}" for k, v in migrate_body_html(conn).items()))


def insert_run(conn, posting_id: int, r: dict, inp: dict | None, path: str, cap_id: dict, tech_id: dict) -> dict | None:
    """추출 결과 하나 -> 추출 실행 + 자리·한 줄·요건·요건 기술. 이미 넣은 결과면 None."""
    model = r["model"]
    pv = r.get("prompt_version") or "unknown"
    dv = r.get("dict_version") or "unknown"
    ih = r.get("input_hash") or (sha256(llm_input(inp)) if inp else "0" * 64)
    if conn.execute("""SELECT 1 FROM extraction_run WHERE posting_id = %s AND model = %s AND prompt_version = %s
                       AND dict_version = %s AND input_hash = %s""", (posting_id, model, pv, dv, ih)).fetchone():
        return None
    pin, pout = PRICES.get(model, (0, 0))
    cost = r.get("cost_usd", round(r["input_tokens"] / 1e6 * pin + r["output_tokens"] / 1e6 * pout, 6))
    run_at = r.get("run_at") or datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat()
    retried = (r.get("checks") or {}).get("retry") is not None
    conn.execute("UPDATE extraction_run SET is_current = false WHERE posting_id = %s AND is_current", (posting_id,))
    run_id = conn.execute(
        """INSERT INTO extraction_run (posting_id, model, prompt_version, dict_version, input_hash, input_tokens, output_tokens,
                                       cost_usd, retried, review_reasons, llm_output_raw, is_current, run_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s) RETURNING id""",
        (posting_id, model, pv, dv, ih, r["input_tokens"], r["output_tokens"], cost, retried,
         Jsonb(review_reasons(r)), Jsonb(r["llm_output_raw"]) if r.get("llm_output_raw") is not None else None,
         run_at)).fetchone()[0]

    n = {"자리": 0, "한 줄": 0, "요건": 0, "요건 기술": 0}
    for useq, pos in enumerate(r["positions"], 1):
        lo, hi = parse_years(pos.get("years", ""))
        unit_id = conn.execute(
            """INSERT INTO recruit_unit (run_id, seq, name, is_it, career, years_text, min_years, max_years)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (run_id, useq, pos["name"], pos.get("it_job", True) is not False, pos["career"], pos.get("years", ""), lo, hi)).fetchone()[0]
        n["자리"] += 1
        if pos.get("it_job") is False:  # IT 가 아닌 자리는 이름·경력만
            continue
        for cat in CATS:
            for iseq, it in enumerate(pos.get(cat, []), 1):
                item_id = conn.execute("""INSERT INTO unit_item (unit_id, category, seq, text, quote)
                                          VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                                       (unit_id, CAT_KO[cat], iseq, it["text"], it.get("quote") or it["text"])).fetchone()[0]
                n["한 줄"] += 1
                for rq in it["reqs"]:
                    cap, other = rq["capability"], ""
                    if cap.startswith(OTHER + ":"):
                        cap, other = OTHER, cap.split(":", 1)[1].strip()
                    elif cap not in cap_id:  # 사전에 없는 능력 이름은 '기타'로
                        cap, other = OTHER, cap
                    if cap not in cap_id:
                        raise RuntimeError("사전이 비어 있습니다. 먼저 'db_load.py sync-dict' 를 실행하세요.")
                    req_id = conn.execute("""INSERT INTO requirement (item_id, capability_id, other_name, relation)
                                             VALUES (%s, %s, %s, %s) RETURNING id""",
                                          (item_id, cap_id[cap], other, rq["relation"])).fetchone()[0]
                    n["요건"] += 1
                    if rq["relation"] == "능력만":  # 능력만이면 요건 기술 없음
                        continue
                    for e in rq["techs"]:
                        conn.execute("INSERT INTO requirement_tech (requirement_id, tech_id, written_name) VALUES (%s, %s, %s)",
                                     (req_id, tech_id.get(e["name"]) if e.get("kind") == "tech" else None, e.get("raw") or e["name"]))
                        n["요건 기술"] += 1
    return n


def save_posting(conn, t: dict, path: str, imgs: dict, kept: dict, inputs: dict, cap_id: dict, tech_id: dict) -> dict[str, int]:
    """공고 하나를 한 트랜잭션으로(공고·이미지·추출 실행·요건). 실패하면 통째로 되돌려진다. 넣은 수를 돌려준다."""
    rid, c = t["rec_idx"], {}
    add = lambda k, v=1: c.__setitem__(k, c.get(k, 0) + v)
    with conn.transaction():
        pid = upsert_posting(conn, t, update_raw=os.path.exists(path))
        add("공고")
        add("이미지", upsert_images(conn, pid, imgs.get(rid, []), kept))
        if not os.path.exists(path):
            print(f"  {rid}: 추출 결과 없음(공고만 넣음)")
            return c
        n = insert_run(conn, pid, json.load(open(path, encoding="utf-8")), inputs.get(rid), path, cap_id, tech_id)
        if n is None:
            add("추출 실행(이미 있음)")
            return c
        add("추출 실행(새로)")
        for k, v in n.items():
            add(k, v)
    return c


def load(run: str) -> tuple[dict[str, int], list[str], dict[str, str]]:
    """targets.tsv 의 공고·이미지와 out/extract/<run>/ 의 추출 결과를 넣는다. (넣은 수, 저장 실패한 공고번호, {번호: 원인}).
    추출 결과 폴더가 없어도(비용 상한·실패) 공고·이미지는 넣는다 — 다음 ① 때 '밀린 공고'로 다시 추출된다.
    공고마다 따로 저장한다. 연결 끊김·교착 같은 일시 오류는 그 공고를 SAVE_TRIES 번까지 다시 하고(끊긴 연결은 다시 연결),
    다시 해도 같은 오류(데이터·사전 문제)는 그 공고만 건너뛰고 나머지를 계속 넣는다."""
    run_dir = os.path.join(EX, run)
    targets = load_targets()
    inputs_path = os.path.join(EX, "_inputs.json")
    inputs = json.load(open(inputs_path, encoding="utf-8")) if os.path.exists(inputs_path) else {}
    imgs, kept = image_rows(), kept_by_image()
    total = {"공고": 0, "이미지": 0, "추출 실행(새로)": 0, "추출 실행(이미 있음)": 0, "자리": 0, "한 줄": 0, "요건": 0, "요건 기술": 0,
             "저장 실패": 0}
    failed: list[str] = []
    why: dict[str, str] = {}
    if not targets:
        return total, failed, why
    conn = connect()
    try:
        cap_id = dict(conn.execute("SELECT name, id FROM capability").fetchall())
        tech_id = dict(conn.execute("SELECT name, id FROM tech").fetchall())
        conn.commit()
        for t in targets:
            rid = t["rec_idx"]
            if not os.path.exists(os.path.join(PAGE_DIR, f"{rid}.html")):
                print(f"  {rid}: 본문 파일이 없어 건너뜀")
                continue
            path = os.path.join(run_dir, f"{rid}.json")
            for attempt in range(1, SAVE_TRIES + 1):
                try:
                    c = save_posting(conn, t, path, imgs, kept, inputs, cap_id, tech_id)
                except psycopg.OperationalError as e:  # 연결 끊김·교착·직렬화 실패 — 다시 하면 될 수 있다
                    print(f"  {rid}: 저장 실패({attempt}/{SAVE_TRIES}) {type(e).__name__}: {str(e)[:200]}", flush=True)
                    if attempt == SAVE_TRIES:
                        failed.append(rid)
                        why[rid] = f"{type(e).__name__}({SAVE_TRIES}번 다시 해도)"
                        break
                    if conn.closed or conn.broken:
                        conn = connect()
                    time.sleep(RETRY_WAIT * attempt)
                    continue
                except Exception as e:  # 데이터·사전 문제 — 다시 해도 같으니 그 공고만 건너뛴다
                    print(f"  {rid}: 저장 실패(다시 해도 같은 오류) {type(e).__name__}: {str(e)[:200]}", flush=True)
                    failed.append(rid)
                    why[rid] = type(e).__name__
                    break
                for k, v in c.items():
                    total[k] += v
                break
    finally:
        conn.close()
    total["저장 실패"] = len(failed)
    return total, failed, why


def cmd_load(run: str) -> None:
    """저장하고 결과를 <데이터>/out/load_result.json 에 쓴다(Airflow 태스크가 읽음). 저장 실패가 남으면 종료 코드 1."""
    total, failed, why = load(run)
    print(" · ".join(f"{k} {v}" for k, v in total.items()))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "load_result.json"), "w", encoding="utf-8") as f:
        json.dump({"total": total, "failed": failed, "why": why}, f, ensure_ascii=False)
    if failed:
        print(f"저장 실패 {len(failed)}건: {', '.join(failed)}", flush=True)
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="DB 저장(Load)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="표 만들기(db/schema.sql)")
    sub.add_parser("migrate-body-html", help="한 번만: 본문 HTML 칸 채우기 + 노트북 경로 칸 빼기")
    sub.add_parser("sync-dict", help="capabilities.json -> 사전 표")
    e = sub.add_parser("export-dict", help="DB 사전 -> db/seed_dictionary.sql (빈 DB·테스트용, 내려받아 커밋)")
    e.add_argument("--out", default=SEED_SQL, help="쓸 파일 (기본 db/seed_dictionary.sql)")
    p = sub.add_parser("load", help="공고·이미지·추출 결과 넣기 (데이터 폴더는 OCR_DATA_DIR)")
    p.add_argument("--run", required=True, help="out/extract/ 아래 결과 폴더 이름 (예: gpt-5.6-luna-ex-chk)")
    args = ap.parse_args()
    if args.cmd == "init":
        cmd_init()
    elif args.cmd == "sync-dict":
        cmd_sync_dict()
    elif args.cmd == "export-dict":
        cmd_export_dict(args.out)
    elif args.cmd == "migrate-body-html":
        cmd_migrate_body_html()
    else:
        cmd_load(args.run)


if __name__ == "__main__":
    main()
