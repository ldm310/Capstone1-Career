import json
import unittest
from pathlib import Path
from external_pass_crawler.platforms.linkareer_parser import parse_search, parse_detail
from external_pass_crawler.privacy import technical_summary
from external_pass_crawler.errors import ParseError
from external_pass_crawler.classification import relation, same_company, canonical_role

FIXTURES = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def html(self, name):
        return (FIXTURES / name).read_text(encoding="utf-8")

    def test_search_fixture_reads_only_public_identity_fields(self):
        page = parse_search(self.html("search.html"))
        self.assertEqual(page.total, 3)
        self.assertEqual(page.candidates[0].external_id, "101")
        self.assertEqual(page.candidates[0].company, "테스트테크")
        self.assertFalse(hasattr(page.candidates[0], "authorName"))

    def test_detail_fixture_identity_and_privacy_summary(self):
        detail = parse_detail(self.html("detail.html"), "101")
        summary = technical_summary(detail.content)
        for personal in ("가상작성자", "fictional@", "010-", "가상학교"):
            self.assertNotIn(personal, summary)
        for tech in ("Python", "Spring", "Redis"):
            self.assertIn(tech, summary)
        self.assertNotIn("가상작성자", repr(parse_search(self.html("search.html"))))

    def test_empty_is_distinct_from_layout_failure_or_login(self):
        self.assertEqual(parse_search(self.html("empty.html")).total, 0)
        for html in (self.html("login.html"), "<html>layout changed</html>"):
            with self.assertRaises(ParseError):
                parse_search(html)
        with self.assertRaises(ParseError):
            parse_detail(self.html("detail.html"), "999")

    def test_technical_summary_is_allowlist_only(self):
        self.assertEqual(json.loads(technical_summary("임의 이름과 연락처가 있는 자기소개")), {"technologies": [], "technologySignals": [], "projectSignals": []})

    def test_relations_prioritize_exact_then_family_then_it_domain(self):
        self.assertEqual(relation("백엔드 개발", "서버 개발자"), "EXACT_ROLE")
        self.assertEqual(relation("백엔드 개발", "프론트엔드 개발"), "SAME_JOB_FAMILY")
        self.assertEqual(relation("백엔드 개발", "데이터 엔지니어"), "SAME_IT_DOMAIN")
        self.assertEqual(relation("백엔드 개발", "인사"), "EXCLUDED")
        self.assertEqual(relation("영업", "백엔드"), "EXCLUDED")
        self.assertIsNone(canonical_role("반도체 공정기술 Python"))
        self.assertEqual(canonical_role("backend"), "backend")

    def test_company_identity_never_uses_substring_or_fuzzy_match(self):
        self.assertTrue(same_company("주식회사 테스트테크", "(주) 테스트테크"))
        self.assertFalse(same_company("테스트테크", "테스트테크솔루션"))
        self.assertFalse(same_company("삼성전자", "삼성SDS"))
        self.assertTrue(same_company("테스트테크", "TestTech", ["TestTech"]))

    def test_parser_fixtures_distinguish_basic_use_from_project_execution(self):
        cases = (
            ("detail_basic_use.html", ["BASIC_USE"]),
            ("detail_project_signals.html", ["FEATURE_IMPLEMENTATION", "TESTING", "DEPLOYMENT"]),
        )
        for fixture, signals in cases:
            with self.subTest(fixture=fixture):
                material = parse_detail(self.html(fixture), "101")
                serialized = technical_summary(material.content)
                data = json.loads(serialized)
                self.assertEqual(data["technologies"], ["Spring", "Docker"])
                self.assertEqual(data["projectSignals"], signals)
                self.assertEqual(data["technologySignals"], [] if fixture == "detail_basic_use.html" else [
                    {"technology": "Spring", "signals": ["FEATURE_IMPLEMENTATION", "TESTING"]},
                    {"technology": "Docker", "signals": ["DEPLOYMENT"]}])
                for private in ("가상작성자", "가상학교", "fictional@", "010-", "구현했습니다", "배포했습니다"):
                    self.assertNotIn(private, serialized)
