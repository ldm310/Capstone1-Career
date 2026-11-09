from dataclasses import dataclass, asdict
from .classification import canonical_role, relation, same_company
from .models import StoredMaterial
from .privacy import technical_summary, prose_text
from .errors import CrawlerError, ParseError


@dataclass
class CollectionResult:
    examined: int = 0
    foreign_company: int = 0
    excluded: int = 0
    accepted: int = 0
    truncated: bool = False


def collect(adapter, company, postings, max_records, max_pages, aliases=(), *, preserve_text=False):
    result, saved, seen = CollectionResult(), [], set()
    priority = {"EXACT_ROLE": 0, "SAME_JOB_FAMILY": 1, "SAME_IT_DOMAIN": 2, "EXCLUDED": 3}
    targets = [(p["site_job_category"] or "") + " " + p["title"] for p in postings]
    for page in range(1, max_pages + 1):
        listing = adapter.search(company, page)
        if not listing.candidates:
            break
        ordered = sorted(listing.candidates, key=lambda c: min(
            (priority[relation(target, c.role)] for target in targets), default=3))
        new = [c for c in ordered if c.external_id not in seen]
        if not new:
            raise ParseError("Repeated search page")
        for candidate in new:
            if result.examined >= max_records:
                result.truncated = True
                break
            seen.add(candidate.external_id)
            result.examined += 1
            if not same_company(company, candidate.company, aliases):
                result.foreign_company += 1
                continue
            if canonical_role(candidate.role) is None:
                result.excluded += 1
                continue
            detail = adapter.detail(candidate.external_id)
            if not same_company(company, detail.company, aliases):
                result.foreign_company += 1
                continue
            role = canonical_role(detail.role)
            if role is None:
                result.excluded += 1
                continue
            body = prose_text(detail.content) if preserve_text else None
            if preserve_text and (not body or len(body) > 200_000):
                raise ParseError("Public essay text is empty or too large")
            saved.append(StoredMaterial(detail.external_id, role, technical_summary(detail.content), body))
            result.accepted += 1
        if result.examined >= max_records or len(seen) >= listing.total:
            result.truncated = len(seen) < listing.total
            break
        if page == max_pages:
            result.truncated = True
    return saved, result


def run_task(repo, adapter, task, max_records, max_pages, aliases=()):
    try:
        materials, result = collect(adapter, task["name"], repo.postings(task["company_id"]),
                                    max_records, max_pages, aliases)
        status, total = repo.finish(task, materials)
        return {"company_id": task["company_id"], "status": status, "total_materials": total, **asdict(result)}
    except Exception as exc:
        code = exc.code if isinstance(exc, CrawlerError) else "COLLECTION_FAILED"
        repo.fail(task, code)
        return {"company_id": task["company_id"], "status": "FAILED", "error_code": code}
