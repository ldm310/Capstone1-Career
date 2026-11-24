"""
파이프라인이 다음에 할 일을 정하려고 DB(public 스키마)에서 읽고 쓰는 함수들.
웹에 보여 주기 위한 조회·뷰는 BE 몫이라 여기 두지 않는다.

  - 진행 공고: status = '진행' AND (마감일 없음 OR 마감일 >= 오늘 KST)
  - 밀린 공고: 진행 공고 가운데 추출 실행이 하나도 없거나, 현재 결과를 사람이 '다시'로 돌려보낸 공고
  - 사람 검토(extraction_run.review_result): 정상 / 제외(변경·마감 확인도 하지 않음) / 다시(피드백을 붙여 다시 추출)
연결은 db_load.connect() 를 쓴다(search_path=public). 쓰는 함수는 스스로 트랜잭션을 연다.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
SITE = "사람인"
# targets.tsv 와 같은 칸
TARGET_COLS = """p.site_posting_no AS rec_idx, c.name AS company, p.title, coalesce(p.site_job_category, '') AS role,
                 coalesce(p.career_condition, '') AS career, coalesce(to_char(p.deadline, 'YYYY-MM-DD'), '') AS deadline"""
OPEN = "p.status = '진행' AND (p.deadline IS NULL OR p.deadline >= %(today)s)"


def today_kst() -> dt.date:
    return dt.datetime.now(KST).date()


def _rows(cur) -> list[dict]:
    names = [d.name for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def known_posting_nos(conn) -> set[str]:
    """DB 에 있는 공고의 공고번호('아는 번호'). 버린 공고(교육생 등)는 기억하지 않고 매일 목록에서 다시 거른다."""
    cur = conn.execute("SELECT site_posting_no FROM posting WHERE site = %(s)s", {"s": SITE})
    return {r[0] for r in cur.fetchall()}


def pending_postings(conn) -> list[dict]:
    """밀린 공고: 진행 공고 가운데 추출 실행이 하나도 없거나, 현재 결과를 사람이 '다시'로 돌려보낸 공고.
    feedback 칸 = 돌려보낸 공고의 사람 피드백(다시 추출할 때 LLM 입력 끝에 붙음), 나머지는 ''.
    공고 정보(직무·경력·마감일)는 DB 에서 읽는다. 공고번호 오름차순(오래된 것 먼저)."""
    cur = conn.execute(f"""SELECT {TARGET_COLS}, '' AS kind, '' AS text_chars, '' AS images,
                                  CASE WHEN e.review_result = '다시' THEN e.review_feedback ELSE '' END AS feedback
                           FROM posting p JOIN company c ON c.id = p.company_id
                                LEFT JOIN extraction_run e ON e.posting_id = p.id AND e.is_current
                           WHERE p.site = %(s)s AND {OPEN}
                             AND (NOT EXISTS (SELECT 1 FROM extraction_run x WHERE x.posting_id = p.id)
                                  OR e.review_result = '다시')
                           ORDER BY length(p.site_posting_no), p.site_posting_no""",
                       {"s": SITE, "today": today_kst()})
    return _rows(cur)


def open_postings(conn) -> list[dict]:
    """진행 공고 (② 수정 확인 대상). targets 칸 + raw_hash + last_checked_at + recheck_due(다시 확인할 공고).
    사람이 '제외'한 공고(현재 결과의 검토 결과)는 빼서 변경·마감 확인을 하지 않는다."""
    cur = conn.execute(f"""SELECT {TARGET_COLS}, p.raw_hash, p.last_checked_at, p.recheck_due
                           FROM posting p JOIN company c ON c.id = p.company_id
                           WHERE p.site = %(s)s AND {OPEN}
                             AND NOT EXISTS (SELECT 1 FROM extraction_run e
                                             WHERE e.posting_id = p.id AND e.is_current AND e.review_result = '제외')
                           ORDER BY p.site_posting_no""",
                       {"s": SITE, "today": today_kst()})
    return _rows(cur)


def mark_closed(conn, nos: list[str]) -> int:
    """본문이 없어진 공고를 '마감'으로 바꾼다."""
    if not nos:
        return 0
    with conn.transaction():
        return conn.execute("""UPDATE posting SET status = '마감' WHERE site = %s AND site_posting_no = ANY(%s)""",
                            (SITE, list(nos))).rowcount


def update_deadlines(conn, deadlines: dict[str, dt.date]) -> int:
    """② 가 목록에서 읽은 마감일로 바꾼다(상태 '진행'이고 값이 다를 때만). 마감일은 본문 밖이라 본문 지문이 같아도 바뀔 수 있다.
    DB 마감일이 이미 지났어도 목록에 보이면(연장) 바꾼다. 바꾼 수를 돌려준다."""
    if not deadlines:
        return 0
    with conn.transaction():
        return conn.execute("""UPDATE posting p SET deadline = v.d
                               FROM unnest(%s::text[], %s::date[]) AS v(no, d)
                               WHERE p.site = %s AND p.site_posting_no = v.no AND p.status = '진행'
                                 AND p.deadline IS DISTINCT FROM v.d""",
                            (list(deadlines), list(deadlines.values()), SITE)).rowcount


def mark_recheck_due(conn, nos: list[str]) -> int:
    """'수정'으로 고른 공고를 '다시 확인할 공고'로 표시한다 — 확인을 마치거나 다시 저장하면 지워진다(실패하면 다음 날 다시)."""
    if not nos:
        return 0
    with conn.transaction():
        return conn.execute("UPDATE posting SET recheck_due = true WHERE site = %s AND site_posting_no = ANY(%s)",
                            (SITE, list(nos))).rowcount


def touch_checked(conn, nos: list[str], at: dt.datetime | None = None) -> int:
    """다시 확인했더니 본문이 그대로인 공고의 마지막 확인 시각을 at(본문을 받은 시각, 없으면 지금)으로. 다시 확인할 표시도 지운다."""
    if not nos:
        return 0
    with conn.transaction():
        return conn.execute("""UPDATE posting SET last_checked_at = coalesce(%s, now()), recheck_due = false
                               WHERE site = %s AND site_posting_no = ANY(%s)""", (at, SITE, list(nos))).rowcount


def day_cost(conn, day: dt.date) -> tuple[float, int]:
    """KST 그날(00:00~24:00) 추출 실행의 비용 합(달러)과 실행 수."""
    start = dt.datetime.combine(day, dt.time(), tzinfo=KST)
    end = start + dt.timedelta(days=1)
    usd, n = conn.execute("""SELECT coalesce(sum(cost_usd), 0), count(*) FROM extraction_run
                             WHERE run_at >= %s AND run_at < %s""", (start, end)).fetchone()
    return float(usd), int(n)
