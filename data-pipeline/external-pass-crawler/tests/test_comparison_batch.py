import copy
import unittest
from unittest.mock import Mock, patch
from external_pass_crawler.comparison_batch import consume, low_allowed
from external_pass_crawler.comparison_requests import validate_selection
from external_pass_crawler.classification import canonical_role
from external_pass_crawler.errors import AccessRestricted, ContractError


def selected():
    return {"postingId": 1, "recruitUnitId": 11, "selectionStatus": "SELECTED", "roleCode": "backend",
            "policyVersion": "keyword-mvp-2", "appliedCriteria": {"jobFamilyExpansionEnabled": False},
            "candidates": [{"postingId": 3, "recruitUnitId": 31, "companyId": 2, "rank": 1,
                            "confidence": "HIGH", "featureMode": "REQUIRED", "evidenceCount": 2}]}


def row(company, confidence="HIGH", status=None, rank=1, request=1):
    return {"id": company, "request_id": request, "candidate_company_id": company,
            "candidate_posting_id": company * 10, "candidate_recruit_unit_id": company * 100,
            "confidence": confidence, "status": status, "candidate_rank": rank}


class FakeRepository:
    def __init__(self, rows, ids=None):
        self.rows = rows
        self.ids = ids or {}
        self.enqueued, self.claimed, self.relinked, self.marked = [], [], [], []

    def candidates(self, request_ids):
        return sorted(copy.deepcopy(self.rows), key=lambda r: (r["confidence"] != "HIGH", r["candidate_rank"]))

    def platform_restricted(self):return False

    def material_ids(self, r):
        return self.ids.get(r["candidate_company_id"], set())

    def enqueue(self, company):
        self.enqueued.append(company)

    def claim(self, company):
        self.claimed.append(company)
        return {"company_id": company}

    def link_candidate(self, candidate):
        self.relinked.append(candidate['candidate_company_id'])

    def mark_requested(self, r, reused):
        self.marked.append((r["id"], reused))


class ComparisonBatchTests(unittest.TestCase):
    def test_only_backend_response_is_accepted_and_role_ambiguity_is_excluded(self):
        self.assertEqual(validate_selection(selected(), 1, 11)["candidates"][0]["confidence"], "HIGH")
        self.assertIsNone(canonical_role("백엔드 프론트엔드"))
        self.assertEqual(canonical_role("backend"), "backend")

    def test_family_expansion_identity_duplicates_and_invalid_evidence_are_rejected(self):
        for change in (lambda d: d.update(postingId=9),
                       lambda d: d["appliedCriteria"].update(jobFamilyExpansionEnabled=True),
                       lambda d: d["candidates"].append(copy.deepcopy(d["candidates"][0])),
                       lambda d: d["candidates"][0].update(evidenceCount=1),
                       lambda d: d["candidates"][0].update(featureMode="FALLBACK_FEATURES")):
            value=selected();change(value)
            with self.assertRaises(ContractError):validate_selection(value,1,11)

    def test_high_is_consumed_before_low_even_if_low_has_a_better_rank(self):
        repo=FakeRepository([row(2,"LOW",rank=1),row(3,"HIGH",rank=2)])
        def task(repo, adapter, task, *limits):
            for r in repo.rows:
                if r["candidate_company_id"]==task["company_id"]:r["status"]="INSUFFICIENT"
            return {"status":"INSUFFICIENT"}
        with patch('external_pass_crawler.comparison_batch.run_task',side_effect=task):consume(repo,Mock(),[1])
        self.assertEqual(repo.claimed,[3,2])

    def test_sufficient_high_materials_do_not_register_or_crawl_low(self):
        repo=FakeRepository([row(2,"HIGH","READY"),row(3,"LOW")],{2:{1,2,3,4,5}})
        with patch('external_pass_crawler.comparison_batch.run_task') as task:consume(repo,Mock(),[1])
        self.assertFalse(repo.enqueued);task.assert_not_called()
        self.assertEqual(repo.marked,[(2,True)])

    def test_high_pending_or_running_blocks_low(self):
        for state in (None,"PENDING","RUNNING"):
            rows=[row(2,"HIGH",state),row(3,"LOW")]
            self.assertFalse(low_allowed(FakeRepository(rows),rows[1],rows))

    def test_ready_insufficient_failed_are_reused_without_automatic_retry(self):
        for state in ("READY","INSUFFICIENT","FAILED"):
            repo=FakeRepository([row(2,status=state)],{2:{1}})
            with patch('external_pass_crawler.comparison_batch.run_task') as task:consume(repo,Mock(),[1])
            task.assert_not_called();self.assertEqual(repo.relinked,[2]);self.assertEqual(repo.marked,[(2,True)])

    def test_running_does_not_enqueue_or_claim(self):
        repo=FakeRepository([row(2,status="RUNNING")])
        consume(repo,Mock(),[1]);self.assertFalse(repo.enqueued);self.assertFalse(repo.claimed)

    def test_batch_cannot_start_more_than_three_companies(self):
        repo=FakeRepository([row(i,request=i) for i in range(2,8)])
        with patch('external_pass_crawler.comparison_batch.run_task',return_value={"status":"INSUFFICIENT"}):
            result=consume(repo,Mock(),list(range(2,8)))
        self.assertEqual(result['processed_companies'],3);self.assertEqual(len(repo.enqueued),3)

    def test_company_shared_by_candidates_is_only_claimed_once(self):
        repo=FakeRepository([row(2),row(2,rank=2)])
        with patch('external_pass_crawler.comparison_batch.run_task',return_value={"status":"READY"}):consume(repo,Mock(),[1])
        self.assertEqual(repo.claimed,[2])

    def test_access_restriction_stops_the_whole_batch(self):
        repo=FakeRepository([row(2),row(3)])
        with patch('external_pass_crawler.comparison_batch.run_task',return_value={"status":"FAILED","error_code":"ACCESS_RESTRICTED"}) as task:
            with self.assertRaises(AccessRestricted):consume(repo,Mock(),[1])
        self.assertEqual(task.call_count,1)

    def test_limits_are_enforced_before_any_repository_access(self):
        for limits in ((4,100,5),(3,101,5),(3,100,6)):
            repo=Mock()
            with self.assertRaises(ContractError):consume(repo,Mock(),[1],*limits)
            repo.candidates.assert_not_called()

    def test_previous_access_restriction_is_not_retried_on_another_company(self):
        blocked=row(2,status="FAILED");blocked['error_code']='ACCESS_RESTRICTED'
        repo=FakeRepository([blocked,row(3)])
        with self.assertRaises(AccessRestricted):consume(repo,Mock(),[1])
        self.assertFalse(repo.enqueued)

    def test_stored_materials_without_a_task_are_reused_without_crawling(self):
        stored=row(2);stored['stored_count']=5
        repo=FakeRepository([stored],{2:{1,2,3,4,5}})
        with patch('external_pass_crawler.comparison_batch.run_task') as task:consume(repo,Mock(),[1])
        task.assert_not_called();self.assertFalse(repo.claimed);self.assertEqual(repo.marked,[(2,True)])

    def test_platform_restriction_from_another_request_blocks_new_network_work(self):
        repo=FakeRepository([row(2)]);repo.platform_restricted=lambda:True
        with self.assertRaises(AccessRestricted):consume(repo,Mock(),[1])
        self.assertFalse(repo.enqueued)

    def test_register_only_queues_high_without_claiming_or_network_calls(self):
        repo=FakeRepository([row(2),row(3,'LOW')]);adapter=Mock()
        with patch('external_pass_crawler.comparison_batch.run_task') as task:
            result=consume(repo,adapter,[1],run_crawlers=False)
        self.assertEqual(result['queued_or_pending_companies'],1)
        self.assertEqual(repo.enqueued,[2]);self.assertFalse(repo.claimed)
        task.assert_not_called();adapter.search.assert_not_called()
