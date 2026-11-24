"""Admin review queue. No LLM requests here; enabled only for an explicitly configured namespace."""
from __future__ import annotations

import datetime as dt
import os
from urllib.parse import quote
from uuid import uuid4

from psycopg.rows import dict_row


class ReviewQueue:
    def __init__(self, namespace, connector):
        self.namespace, self.connect = namespace, connector

    @classmethod
    def configured(cls):
        # Deferred import avoids db_load -> extract_skills -> db_load at module load.
        from db_load import _env_file, connect
        namespace = os.environ.get("CAREER_PIPELINE_NAMESPACE", _env_file().get("CAREER_PIPELINE_NAMESPACE", ""))
        return cls(namespace, connect) if namespace and namespace.lower() != "off" else None

    def requested(self, posting_no):
        with self.connect() as conn:
            row = conn.execute("SELECT status FROM public.career_extraction_review WHERE namespace=%s AND site='사람인' AND posting_no=%s", (self.namespace, posting_no)).fetchone()
            return bool(row and row[0] == "RETRY_REQUESTED")

    def targets(self, rows):
        """Include explicit requests even when a failed new posting was never loaded into posting."""
        with self.connect() as conn:
            saved = conn.cursor(row_factory=dict_row).execute("SELECT * FROM public.career_extraction_review WHERE namespace=%s", (self.namespace,)).fetchall()
        by_no = {row["posting_no"]: row for row in saved if row["site"] == "사람인"}
        result = [row for row in rows if not (by_no.get(row["rec_idx"], {}).get("status") == "SKIPPED" or
                  (by_no.get(row["rec_idx"], {}).get("status") == "OPEN" and by_no[row["rec_idx"]]["failure_count"] >= 2))]
        present = {row["rec_idx"] for row in result}
        now = dt.datetime.now(dt.timezone.utc)
        for row in by_no.values():
            expired = row["status"] == "RUNNING" and row["claimed_at"] and now-row["claimed_at"] > dt.timedelta(hours=1)
            if (row["status"] == "RETRY_REQUESTED" or expired) and row["posting_no"] not in present:
                result.append({"rec_idx":row["posting_no"],"company":row["company"],"title":row["title"],"role":"","career":"","deadline":"","kind":"","text_chars":"","images":""})
        return result

    def begin(self, posting_no, inp):
        """Claim one attempt; two failures suspend automatic retries. Feedback requests bypass that gate once."""
        with self.connect() as conn, conn.transaction():
            conn.execute("""INSERT INTO public.career_extraction_review(namespace,site,posting_no,company,title,source_url)
                VALUES(%s,'사람인',%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (self.namespace,posting_no,inp.get("company", ""),inp.get("title", ""),"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx="+quote(posting_no,safe="")))
            row = conn.cursor(row_factory=dict_row).execute("SELECT * FROM public.career_extraction_review WHERE namespace=%s AND site='사람인' AND posting_no=%s FOR UPDATE", (self.namespace,posting_no)).fetchone()
            if row["status"] == "SKIPPED":
                return None
            if row["status"] == "RUNNING":
                if row["claimed_at"] and dt.datetime.now(dt.timezone.utc)-row["claimed_at"] <= dt.timedelta(hours=1):
                    return None
                row["failure_count"] += 1
                row["status"] = "OPEN"
                conn.execute("UPDATE public.career_extraction_review SET status='OPEN',failure_count=%s,error_code='이전 실행 중단',last_failed_at=now(),revision=revision+1 WHERE id=%s", (row["failure_count"],row["id"]))
            if row["status"] != "RETRY_REQUESTED" and row["failure_count"] >= 2:
                return None
            attempt = str(uuid4())
            feedback = row["feedback"] if row["status"] == "RETRY_REQUESTED" else ""
            conn.execute("UPDATE public.career_extraction_review SET status='RUNNING',attempt_id=%s,claimed_at=now(),updated_at=now(),revision=revision+1 WHERE id=%s", (attempt,row["id"]))
            conn.execute("INSERT INTO public.career_extraction_review_event(id,review_id,action) VALUES(%s,%s,'START')", (str(uuid4()),row["id"]))
            return {"id":row["id"],"attempt":attempt,"feedback":feedback}

    def finish(self, ticket, error=None):
        with self.connect() as conn, conn.transaction():
            result = conn.execute("""UPDATE public.career_extraction_review SET status=%s,error_code=%s,
                failure_count=failure_count+%s,last_failed_at=CASE WHEN %s THEN now() ELSE last_failed_at END,
                claimed_at=NULL,updated_at=now(),revision=revision+1 WHERE namespace=%s AND id=%s AND status='RUNNING' AND attempt_id=%s RETURNING id""",
                ("OPEN" if error else "RESOLVED",(error or "")[:160],int(bool(error)),bool(error),self.namespace,ticket["id"],ticket["attempt"]))
            if result.fetchone():
                conn.execute("INSERT INTO public.career_extraction_review_event(id,review_id,action) VALUES(%s,%s,%s)", (str(uuid4()),ticket["id"],"FAIL" if error else "RESOLVE"))
