"""Separate batch: BE selects, PostgreSQL registers, a single crawler consumes work."""
import argparse
import datetime as dt
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .comparison_requests import RequestRepository, validate_selection
from .errors import AccessRestricted, ContractError
from .platforms.linkareer import LinkareerAdapter, PublicHttp
from .runner import run_task
from .policy import MINIMUM_SAMPLE_SIZE


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ContractError("Backend redirect rejected")


def selection(base, posting_id, unit_id):
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContractError("Invalid Backend base URL")
    path = f"/api/postings/{posting_id}/recruit-units/{unit_id}/comparison-candidates"
    with build_opener(NoRedirect()).open(Request(base.rstrip("/") + path, headers={"Accept": "application/json"}), timeout=120) as response:
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ContractError("Backend response too large")
        return validate_selection(json.loads(raw), posting_id, unit_id)


def low_allowed(repo, candidate, rows, minimum=MINIMUM_SAMPLE_SIZE):
    high = [r for r in rows if r["request_id"] == candidate["request_id"] and r["confidence"] == "HIGH"]
    ids = set()
    for row in high:
        ids.update(repo.material_ids(row))
    if len(ids) >= minimum:
        return False
    # Unrequested HIGH work must not be bypassed by a LOW request.
    return all(r["status"] in {"READY", "INSUFFICIENT", "FAILED"} for r in high)


def consume(repo, adapter, request_ids, max_companies=3, max_records=100, max_pages=5, aliases=None,run_crawlers=True):
    if not 1 <= max_companies <= 3 or not 1 <= max_records <= 100 or not 1 <= max_pages <= 5:
        raise ContractError("Batch limits exceed policy")
    processed = set()
    outcomes = []
    # Refresh after HIGH processing, since terminal status and material coverage control LOW.
    for confidence in ("HIGH", "LOW"):
        rows = repo.candidates(request_ids)
        if any(r["status"]=="FAILED" and r.get("error_code")=="ACCESS_RESTRICTED" for r in rows):
            raise AccessRestricted("Previous platform restriction requires manual review")
        for row in rows:
            if row["confidence"] != confidence:
                continue
            if confidence == "LOW" and not low_allowed(repo, row, rows):
                continue
            company = row["candidate_company_id"]
            status = row["status"]
            if status in {"READY", "INSUFFICIENT", "FAILED"}:
                repo.link_candidate(row)
                repo.mark_requested(row, reused=bool(repo.material_ids(row)))
                continue
            if status == "RUNNING":
                repo.mark_requested(row, reused=False)
                continue
            if status is None and row.get("stored_count",0)>0:
                repo.enqueue(company) # Recover a terminal reuse task; no network or RUNNING transition.
                repo.link_candidate(row)
                repo.mark_requested(row,reused=bool(repo.material_ids(row)))
                continue
            if company not in processed and len(processed) >= max_companies:
                continue
            if repo.platform_restricted():
                raise AccessRestricted("Platform restriction requires manual review")
            repo.enqueue(company)
            if company in processed:
                repo.link_candidate(row)
                repo.mark_requested(row,reused=bool(repo.material_ids(row)))
                continue
            processed.add(company)
            repo.mark_requested(row, reused=False)
            if not run_crawlers:
                continue
            task = repo.claim(company)
            if task:
                result = run_task(repo, adapter, task, max_records, max_pages,
                                  (aliases or {}).get(str(company), ()))
                outcomes.append(result)
                if result.get("error_code") == "ACCESS_RESTRICTED":
                    raise AccessRestricted()
                repo.link_candidate(row)
    return {"processed_companies":len(processed) if run_crawlers else 0,
            "queued_or_pending_companies":0 if run_crawlers else len(processed),"outcomes":outcomes}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backend-url", default=os.getenv("BACKEND_URL", "http://backend:8080"))
    p.add_argument("--target-posting-id", type=int)
    p.add_argument("--target-recruit-unit-id", type=int)
    p.add_argument("--since", help="Timezone-aware timestamp; only committed current extraction rows are selected")
    p.add_argument("--max-targets", type=int, default=50)
    p.add_argument("--max-companies", type=int, default=3)
    p.add_argument("--max-records", type=int, default=100)
    p.add_argument("--max-pages", type=int, default=5)
    p.add_argument("--aliases-file", help="Explicit JSON map: company ID -> exact alternative company names")
    p.add_argument("--dry-run", action="store_true", help="Only fetch BE candidate metadata; no enqueue, registration or crawl")
    p.add_argument("--register-only",action="store_true",help="Register provenance and PENDING tasks; never claim or contact a website")
    args = p.parse_args(argv)
    try:
        import psycopg
        from psycopg.rows import dict_row
        if not 1 <= args.max_targets <= 100 or not 1 <= args.max_companies <= 3 or not 1 <= args.max_records <= 100 or not 1 <= args.max_pages <= 5:
            raise ContractError("Invalid batch limits")
        if args.dry_run and args.register_only:raise ContractError("Choose dry-run or register-only")
        explicit = args.target_posting_id is not None or args.target_recruit_unit_id is not None
        if explicit == bool(args.since) or (explicit and (not args.target_posting_id or not args.target_recruit_unit_id or min(args.target_posting_id,args.target_recruit_unit_id) < 1)):
            raise ContractError("Specify one target pair or --since")
        since = dt.datetime.fromisoformat(args.since) if args.since else None
        if since is not None and since.tzinfo is None:
            raise ContractError("--since requires a timezone")
        if not os.environ.get("DATABASE_URL"):
            raise ContractError("DATABASE_URL is required")
        aliases={}
        if args.aliases_file:
            with open(args.aliases_file,encoding="utf-8") as f:aliases=json.load(f)
            if not isinstance(aliases,dict) or any(not isinstance(value,list) or any(not isinstance(x,str) or not x.strip() for x in value) for value in aliases.values()):
                raise ContractError("Invalid explicit company aliases")
        options = "-c default_transaction_read_only=on" if args.dry_run else ""
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, row_factory=dict_row,
                             options=options, connect_timeout=10) as conn:
            repo = RequestRepository(conn)
            repo.check_contract()
            # Session lock also coordinates with the legacy company CLI. Never force-release another worker.
            locked = False
            if not args.dry_run:
                locked = conn.execute("SELECT pg_try_advisory_lock(703114,2) AS locked").fetchone()["locked"]
                if not locked:
                    raise ContractError("Another external crawler is running")
            try:
                targets = [{"posting_id": args.target_posting_id, "unit_id": args.target_recruit_unit_id}] if explicit else repo.saved_targets(since, args.max_targets)
                requests = []
                for target in targets:
                    data = selection(args.backend_url, target["posting_id"], target["unit_id"])
                    if args.dry_run:
                        print(json.dumps({"dry_run": True, "postingId": data["postingId"], "recruitUnitId": data["recruitUnitId"],
                                          "selectionStatus": data["selectionStatus"], "candidateCount": len(data["candidates"])}))
                    else:
                        requests.append(repo.register(data, "MANUAL_BATCH" if explicit else "POSTING_SAVED"))
                if not args.dry_run and requests:
                    result=consume(repo, LinkareerAdapter(PublicHttp(interval=2)), requests,
                                   args.max_companies, args.max_records, args.max_pages, aliases,not args.register_only)
                    print(json.dumps(result))
                    if any(row.get("status")=="FAILED" for row in result["outcomes"]):
                        return 1
            finally:
                if locked:
                    conn.execute("SELECT pg_advisory_unlock(703114,2)")
        return 0
    except Exception as exc:
        print(json.dumps({"error_code": getattr(exc, "code", "BATCH_FAILED")}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
