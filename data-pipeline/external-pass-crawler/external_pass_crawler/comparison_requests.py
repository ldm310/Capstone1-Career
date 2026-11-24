"""Persist BE selection provenance. Similarity is calculated only by the Backend."""
from .errors import ContractError
from .repository import Repository
from .classification import ROLE_RULES

ROLE_CODES = {r[0] for r in ROLE_RULES}


def validate_selection(data, posting_id, unit_id):
    if (data.get("postingId") != posting_id or data.get("recruitUnitId") != unit_id
            or data.get("selectionStatus") not in {"SELECTED", "NO_CANDIDATES", "NOT_COMPARABLE"}
            or not isinstance(data.get("policyVersion"), str) or not data["policyVersion"].strip()
            or data.get("appliedCriteria", {}).get("jobFamilyExpansionEnabled") is not False):
        raise ContractError("Unexpected comparison response")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 5:
        raise ContractError("Unexpected candidate limit")
    seen = set()
    companies = {}
    for c in candidates:
        if data.get("roleCode") not in ROLE_CODES:
            raise ContractError("Unknown standard role code")
        for key in ("postingId", "recruitUnitId", "companyId", "rank", "evidenceCount"):
            if type(c.get(key)) is not int or c[key] < 1:
                raise ContractError("Invalid candidate identifier or evidence")
        if (c["postingId"] in seen or c["postingId"] == posting_id
                or c.get("confidence") not in {"HIGH", "LOW"}
                or c.get("featureMode") not in {"REQUIRED", "FALLBACK_FEATURES"}
                or c["evidenceCount"] < 2
                or (c["featureMode"] == "FALLBACK_FEATURES" and c["confidence"] != "LOW")):
            raise ContractError("Invalid candidate provenance")
        seen.add(c["postingId"])
        companies[c["companyId"]] = companies.get(c["companyId"], 0) + 1
    if len(companies) > 3 or any(n > 2 for n in companies.values()):
        raise ContractError("Unexpected company limit")
    if bool(candidates) != (data["selectionStatus"] == "SELECTED"):
        raise ContractError("Candidate status mismatch")
    return data


class RequestRepository(Repository):
    def check_contract(self):
        super().check_contract()
        from .migrate import check_requests
        check_requests(self.conn)

    def direct_ids(self, posting_id, role_code):
        if role_code not in ROLE_CODES:
            return set()
        return {r["id"] for r in self.conn.execute("""
            SELECT DISTINCT m.id FROM external_data.posting_pass_material l
            JOIN public.posting p ON p.id=l.posting_id JOIN external_data.pass_material m ON m.id=l.material_id
            WHERE p.id=%s AND p.company_id=m.company_id AND m.job_family='IT_SW'
              AND l.relation_type<>'EXCLUDED' AND m.role_name=%s
            """, (posting_id, role_code)).fetchall()}

    def register(self, data, source="MANUAL_BATCH"):
        validate_selection(data, data["postingId"], data["recruitUnitId"])
        if source not in {"MANUAL_BATCH", "POSTING_SAVED"}:
            raise ContractError("Invalid request source")
        with self.conn.transaction():
            self.conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                              ("external-collection-target:"+str(data["recruitUnitId"]),))
            direct = bool(self.direct_ids(data["postingId"], data.get("roleCode")))
            row = self.conn.execute("""
                INSERT INTO external_data.collection_request(target_posting_id,target_recruit_unit_id,
                    standard_role_code,policy_version,selection_status,request_source,used_direct)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(target_recruit_unit_id,policy_version) DO UPDATE SET
                    standard_role_code=excluded.standard_role_code,selection_status=excluded.selection_status,
                    request_source=excluded.request_source,used_direct=excluded.used_direct,updated_at=now()
                RETURNING id
                """, (data["postingId"], data["recruitUnitId"], data.get("roleCode"), data["policyVersion"],
                      data["selectionStatus"], source, direct)).fetchone()
            request_id = row["id"]
            self.conn.execute("UPDATE external_data.collection_candidate SET is_selected=false WHERE request_id=%s",
                              (request_id,))
            if not direct:
                for c in data["candidates"]:
                    self.conn.execute("""
                        INSERT INTO external_data.collection_candidate(request_id,candidate_posting_id,
                            candidate_recruit_unit_id,candidate_company_id,standard_role_code,confidence,
                            feature_mode,evidence_count,candidate_rank)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(request_id,candidate_recruit_unit_id) DO UPDATE SET
                            candidate_posting_id=excluded.candidate_posting_id,
                            candidate_company_id=excluded.candidate_company_id,
                            standard_role_code=excluded.standard_role_code,confidence=excluded.confidence,
                            feature_mode=excluded.feature_mode,evidence_count=excluded.evidence_count,
                            candidate_rank=excluded.candidate_rank,is_selected=true
                        """, (request_id, c["postingId"], c["recruitUnitId"], c["companyId"], data["roleCode"],
                              c["confidence"], c["featureMode"], c["evidenceCount"], c["rank"]))
            return request_id

    def candidates(self, request_ids):
        return self.conn.execute("""
            SELECT c.*,task.status,task.minimum_sample_size,task.error_code,
              (SELECT count(*) FROM external_data.pass_material m WHERE m.company_id=c.candidate_company_id AND m.job_family='IT_SW') AS stored_count
            FROM external_data.collection_candidate c
            JOIN external_data.collection_request q ON q.id=c.request_id
            LEFT JOIN external_data.company_collection task ON task.company_id=c.candidate_company_id
            WHERE c.is_selected AND NOT q.used_direct AND c.request_id=ANY(%s)
            ORDER BY CASE c.confidence WHEN 'HIGH' THEN 0 ELSE 1 END,c.candidate_rank,c.id
            """, (request_ids,)).fetchall()

    def material_ids(self, candidate):
        return {r["id"] for r in self.conn.execute("""
            SELECT DISTINCT m.id FROM external_data.posting_pass_material l
            JOIN public.posting p ON p.id=l.posting_id JOIN external_data.pass_material m ON m.id=l.material_id
            WHERE p.id=%s AND p.company_id=%s AND m.company_id=p.company_id AND m.job_family='IT_SW'
              AND l.relation_type='EXACT_ROLE' AND m.role_name=%s
            """, (candidate["candidate_posting_id"], candidate["candidate_company_id"],
                  candidate["standard_role_code"])).fetchall()}

    def link_candidate(self, candidate):
        # The unit's BE-resolved standard role is authoritative, even on a multi-role posting.
        with self.conn.transaction():
            self.conn.execute("SELECT company_id FROM external_data.company_collection WHERE company_id=%s FOR UPDATE",
                              (candidate["candidate_company_id"],))
            self.conn.execute("""
                INSERT INTO external_data.posting_pass_material(posting_id,material_id,relation_type)
                SELECT c.candidate_posting_id,m.id,'EXACT_ROLE'
                FROM external_data.collection_candidate c
                JOIN public.recruit_unit u ON u.id=c.candidate_recruit_unit_id AND u.is_it=true
                JOIN public.extraction_run r ON r.id=u.run_id AND r.is_current=true AND r.posting_id=c.candidate_posting_id
                JOIN public.posting p ON p.id=c.candidate_posting_id AND p.company_id=c.candidate_company_id
                JOIN external_data.pass_material m ON m.company_id=p.company_id AND m.role_name=c.standard_role_code AND m.job_family='IT_SW'
                WHERE c.id=%s AND c.is_selected=true
                ON CONFLICT(posting_id,material_id) DO UPDATE SET relation_type='EXACT_ROLE',linked_at=now()
                """,(candidate["id"],))

    def mark_requested(self, candidate, reused):
        self.conn.execute("""
            UPDATE external_data.collection_candidate SET requested=true,reused=%s,
                requested_at=coalesce(requested_at,now()) WHERE id=%s AND is_selected=true
            """, (reused, candidate["id"]))

    def saved_targets(self, since, limit):
        return self.conn.execute("""
            SELECT p.id AS posting_id,u.id AS unit_id FROM public.posting p
            JOIN public.extraction_run r ON r.posting_id=p.id AND r.is_current=true
            JOIN public.recruit_unit u ON u.run_id=r.id AND u.is_it=true
            WHERE r.run_at >= %s ORDER BY r.run_at,p.id,u.id LIMIT %s
            """, (since, limit)).fetchall()
