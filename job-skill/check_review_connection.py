"""Read-only readiness check; never runs collection, OCR or an LLM."""
from __future__ import annotations
import json
import sys
from extraction_review import ReviewQueue

def check(queue):
    if queue is None:
        raise ValueError("CAREER_PIPELINE_NAMESPACE is not configured")
    with queue.connect() as conn:
        tables = conn.execute("SELECT to_regclass('public.career_extraction_review') IS NOT NULL,to_regclass('public.career_extraction_review_event') IS NOT NULL,to_regclass('public.posting') IS NOT NULL,to_regclass('public.extraction_run') IS NOT NULL").fetchone()
        if not all(tables):
            raise ValueError("Public posting/extraction tables and migration 008_extraction_review.sql are required")
        counts = dict(conn.execute("SELECT status,count(*) FROM public.career_extraction_review WHERE namespace=%s GROUP BY status", (queue.namespace,)).fetchall())
    return {"connected":True,"namespace":queue.namespace,"reviewCounts":counts,"externalCalls":0}

def main():
    try:
        print(json.dumps(check(ReviewQueue.configured()),ensure_ascii=False))
    except ValueError as error:
        print(str(error),file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Review database connection failed ({type(error).__name__})",file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
