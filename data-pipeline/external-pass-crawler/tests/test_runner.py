import json
import unittest
from unittest.mock import Mock
from external_pass_crawler.models import Candidate, PublicMaterial, SearchPage
from external_pass_crawler.runner import collect, run_task
from external_pass_crawler.errors import AccessRestricted

POSTINGS = [{"id": 1, "title": "백엔드 개발", "site_job_category": "백엔드"}]


class RunnerTests(unittest.TestCase):
    def test_verified_search_alias_keeps_company_and_subsidiary_checks(self):
        adapter = Mock()
        adapter.search.return_value = SearchPage((Candidate('1', 'NHN', '백엔드'),
                                                   Candidate('2', 'NHN AD', '백엔드'),
                                                   Candidate('3', 'NHN', '백엔드')), 3)
        adapter.detail.side_effect = [PublicMaterial('1', 'NHN', '백엔드', 'Python'),
                                      PublicMaterial('3', 'NHN AD', '백엔드', 'Python')]
        saved, result = collect(adapter, '엔에이치엔(주)', POSTINGS, 10, 2,
                                ('NHN',), search_company='NHN', preserve_text=True)
        adapter.search.assert_called_once_with('NHN', 1)
        self.assertEqual([m.external_id for m in saved], ['1'])
        self.assertEqual(result.foreign_company, 2)
        self.assertEqual(saved[0].body_text, 'Python')

    def test_unverified_search_alias_never_requests_upstream(self):
        adapter = Mock()
        with self.assertRaises(ValueError):
            collect(adapter, '회사', POSTINGS, 10, 2, search_company='타사')
        adapter.search.assert_not_called()

    def test_foreign_company_non_it_and_detail_mismatch_are_not_stored(self):
        adapter = Mock()
        adapter.search.return_value = SearchPage((
            Candidate("1", "테스트테크솔루션", "백엔드"), Candidate("2", "테스트테크", "영업"),
            Candidate("3", "테스트테크", "백엔드"), Candidate("4", "테스트테크", "백엔드")), 4)
        adapter.detail.side_effect = [PublicMaterial("3", "타사", "백엔드", "Python"),
                                      PublicMaterial("4", "테스트테크", "백엔드", "가상작성자 Python")]
        saved, result = collect(adapter, "테스트테크", POSTINGS, 10, 2)
        self.assertEqual(len(saved), 1)
        self.assertEqual(result.foreign_company, 2)
        self.assertEqual(result.excluded, 1)
        self.assertNotIn("가상작성자", saved[0].content)
        self.assertEqual(json.loads(saved[0].content), {"technologies": ["Python"], "technologySignals": [], "projectSignals": []})
        self.assertEqual(adapter.detail.call_count, 2)

    def test_limit_and_role_priority(self):
        adapter = Mock()
        adapter.search.return_value = SearchPage((Candidate("3", "회사", "데이터 엔지니어"),
                                                  Candidate("2", "회사", "프론트엔드"),
                                                  Candidate("1", "회사", "백엔드")), 3)
        adapter.detail.return_value = PublicMaterial("1", "회사", "백엔드", "Python")
        saved, result = collect(adapter, "회사", POSTINGS, 1, 5)
        adapter.detail.assert_called_once_with("1")
        self.assertTrue(result.truncated)

    def test_empty_results_finish_insufficient(self):
        repo, adapter = Mock(), Mock()
        repo.postings.return_value = POSTINGS
        repo.finish.return_value = ("INSUFFICIENT", 0)
        adapter.search.return_value = SearchPage((), 0)
        result = run_task(repo, adapter, {"company_id": 1, "name": "회사"}, 10, 2)
        self.assertEqual(result["status"], "INSUFFICIENT")
        repo.finish.assert_called_once_with({"company_id": 1, "name": "회사"}, [])

    def test_access_denied_marks_failed_without_saving_upstream_or_personal_text(self):
        repo, adapter = Mock(), Mock()
        repo.postings.return_value = POSTINGS
        adapter.search.side_effect = AccessRestricted("secret@example.invalid")
        result = run_task(repo, adapter, {"company_id": 1, "name": "회사"}, 10, 2)
        self.assertEqual(result["error_code"], "ACCESS_RESTRICTED")
        self.assertNotIn("secret@", repr(result))
        repo.fail.assert_called_once_with({"company_id": 1, "name": "회사"}, "ACCESS_RESTRICTED")
        repo.finish.assert_not_called()
