import argparse
import json
import math
import os
import sys
from dataclasses import asdict
from .errors import CrawlerError, ContractError, AccessRestricted
from .platforms.linkareer import LinkareerAdapter, PublicHttp
from .runner import collect, run_task


def parser():
    p = argparse.ArgumentParser(description="Company-scoped public Linkareer collection; no DDL or login")
    p.add_argument("--company-id", type=int)
    p.add_argument("--dry-run", action="store_true", help="Read-only DB session; never enqueue, claim or persist")
    p.add_argument("--posting-schema", choices=("job", "public"), default="public")
    p.add_argument("--request-interval", type=float, default=float(os.getenv("EXTERNAL_REQUEST_INTERVAL", "2")))
    p.add_argument("--timeout", type=float, default=float(os.getenv("EXTERNAL_TIMEOUT", "20")))
    p.add_argument("--max-records", type=int, default=int(os.getenv("EXTERNAL_MAX_RECORDS", "100")))
    p.add_argument("--max-pages", type=int, default=int(os.getenv("EXTERNAL_MAX_PAGES", "5")))
    p.add_argument("--max-companies", type=int, default=1)
    p.add_argument("--aliases-file", help="Explicit JSON map: company DB ID -> alternative company names")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if not all(math.isfinite(x) for x in (args.request_interval, args.timeout)) or args.request_interval < 2 or args.timeout <= 0 or not (1 <= args.max_records <= 100 and 1 <= args.max_pages <= 5 and 1 <= args.max_companies <= 3) or (args.company_id is not None and args.company_id < 1):
        p.error("Interval >= 2, pages <= 5, records <= 100, companies <= 3 and positive IDs are required")
    # Use a dedicated BE-compatible DATABASE_URL. Never import job-skill modules or silently choose RDS.
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        p.error("DATABASE_URL is required (never printed)")
    aliases = {}
    if args.aliases_file:
        with open(args.aliases_file, encoding="utf-8") as f:
            aliases = json.load(f)
        if not isinstance(aliases, dict) or any(not isinstance(v, list) or any(not isinstance(x, str) or not x.strip() for x in v) for v in aliases.values()):
            p.error("Aliases must map company IDs to nonempty name lists")
    try:
        import psycopg
        from psycopg.rows import dict_row
        from .repository import Repository
        options = "-c default_transaction_read_only=on" if args.dry_run else ""
        with psycopg.connect(dsn, autocommit=True, row_factory=dict_row, options=options, connect_timeout=10) as conn:
            repo = Repository(conn, args.posting_schema)
            repo.check_contract()
            if not conn.execute("SELECT pg_try_advisory_lock(703114,2) AS locked").fetchone()["locked"]:
                raise ContractError("Another external crawler is running")
            if repo.platform_restricted():
                raise AccessRestricted("Platform restriction requires manual review")
            companies = repo.companies(args.company_id)
            if args.company_id and not companies:
                p.error("Company has no postings in the selected BE database")
            adapter = LinkareerAdapter(PublicHttp(args.request_interval, args.timeout))
            if args.dry_run:
                for company in companies[:args.max_companies]:
                    if company["status"] in ("READY", "INSUFFICIENT", "FAILED", "RUNNING"):
                        print(json.dumps({"company_id": company["id"], "dry_run": True,
                                          "action": "reuse_or_in_progress", "status": company["status"]}))
                        continue
                    _, result = collect(adapter, company["name"], repo.postings(company["id"]),
                                        args.max_records, args.max_pages, aliases.get(str(company["id"]), ()))
                    print(json.dumps({"company_id": company["id"], "dry_run": True, **asdict(result)}))
                return 0
            selected = companies[:args.max_companies]
            for company in selected:
                repo.enqueue(company["id"])
                repo.relink_existing(company["id"])
            failed = False
            for company in selected:
                task = repo.claim(company["id"])
                if task is None:
                    break
                result = run_task(repo, adapter, task, args.max_records, args.max_pages,
                                  aliases.get(str(task["company_id"]), ()))
                print(json.dumps(result))
                failed |= result["status"] == "FAILED"
                if result.get("error_code") == "ACCESS_RESTRICTED":
                    raise AccessRestricted()
            return 1 if failed else 0
    except Exception as exc:
        # Deliberately do not print DSNs, SQL arguments, upstream text or personal data.
        code = exc.code if isinstance(exc, CrawlerError) else "EXECUTION_FAILED"
        print(json.dumps({"error_code": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
