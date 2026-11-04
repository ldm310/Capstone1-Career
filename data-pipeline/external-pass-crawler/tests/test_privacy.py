import json
import unittest
from external_pass_crawler.privacy import technical_summary


class PrivacyTests(unittest.TestCase):
    def payload(self, source):
        return json.loads(technical_summary(source))

    def test_basic_use_does_not_imply_implementation_testing_or_deployment(self):
        for source in ("Spring과 Docker를 사용한 경험이 있습니다.", "Spring과 Docker 사용 경험이 있습니다.", "Spring과 Docker를 사용해 본 경험이 있습니다."):
            with self.subTest(source=source):
                self.assertEqual(self.payload(source), {"technologies": ["Spring", "Docker"], "technologySignals": [], "projectSignals": ["BASIC_USE"]})

    def test_technologies_alone_do_not_infer_any_signal(self):
        self.assertEqual(self.payload("Spring Docker"), {"technologies": ["Spring", "Docker"], "technologySignals": [], "projectSignals": []})

    def test_explicit_implementation_testing_and_deployment_are_distinct(self):
        result = self.payload("Spring으로 기능을 구현했습니다. 단위 테스트를 작성했습니다. Docker로 서비스를 배포했습니다.")
        self.assertEqual(result, {"technologies": ["Spring", "Docker"],
                                  "technologySignals": [
                                      {"technology": "Spring", "signals": ["FEATURE_IMPLEMENTATION"]},
                                      {"technology": "Docker", "signals": ["DEPLOYMENT"]}],
                                  "projectSignals": ["FEATURE_IMPLEMENTATION", "TESTING", "DEPLOYMENT"]})

    def test_every_requested_signal_has_an_explicit_positive_case(self):
        cases = {
            "BASIC_USE": "Python을 사용했습니다.",
            "FEATURE_IMPLEMENTATION": "프로젝트 API 기능을 구현했습니다.",
            "INTEGRATION": "프로젝트의 결제 API를 연동했습니다.",
            "TESTING": "프로젝트의 통합 테스트를 수행했습니다.",
            "SECURITY_RELIABILITY": "서비스의 예외 처리를 구현했습니다.",
            "DEPLOYMENT": "Docker로 서비스를 배포했습니다.",
            "OPERATION": "서비스를 운영했습니다.",
            "OPTIMIZATION": "프로젝트의 응답 시간을 단축했습니다.",
            "ARCHITECTURE": "프로젝트의 서비스 아키텍처를 설계했습니다.",
        }
        for signal, source in cases.items():
            with self.subTest(signal=signal):
                self.assertIn(signal, self.payload(source)["projectSignals"])

    def test_negation_plans_learning_and_requirements_are_not_observations(self):
        cases = [
            "Spring으로 기능을 구현하지 않았습니다.",
            "프로젝트 테스트를 수행한 경험이 없습니다.",
            "Docker로 서비스를 배포하지 못했습니다.",
            "Spring 기능 구현과 Docker 배포를 학습했습니다.",
            "프로젝트 아키텍처 설계를 공부했습니다.",
            "단위 테스트를 작성하고 배포할 계획입니다.",
            "서비스 배포가 필요합니다.",
            "동료가 Spring으로 API를 구현했습니다.",
            "We have not deployed the Docker service.",
            "We plan to implement and test the API.",
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(self.payload(source)["projectSignals"], [])

    def test_noun_lists_and_unknown_actions_do_not_create_signals(self):
        for source in ["Spring 구현 테스트 배포", "Docker라면 운영도 잘할 것입니다.", "프로젝트에서 열심히 협력했습니다."]:
            self.assertEqual(self.payload(source)["projectSignals"], [])

    def test_no_source_sentence_profile_score_or_extra_fields_are_serialized(self):
        source = ("가상작성자 / 가상학교 / 010-0000-0000 / fictional@example.invalid."
                  " Spring으로 비밀프로젝트 기능을 구현했습니다.")
        raw = technical_summary(source)
        data = json.loads(raw)
        self.assertEqual(set(data), {"technologies", "technologySignals", "projectSignals"})
        for forbidden in ("가상작성자", "가상학교", "010-", "fictional@", "비밀프로젝트", "구현했습니다", "LV", "score", "quote"):
            self.assertNotIn(forbidden, raw)

    def test_empty_input_produces_two_empty_arrays(self):
        self.assertEqual(self.payload(""), {"technologies": [], "technologySignals": [], "projectSignals": []})

    def test_signals_are_unique_and_order_is_deterministic(self):
        raw = technical_summary("Spring으로 API를 구현했습니다. Docker로 서비스를 배포했습니다. Spring으로 API를 구현했습니다.")
        self.assertEqual(raw, technical_summary("Spring으로 API를 구현했습니다. Docker로 서비스를 배포했습니다. Spring으로 API를 구현했습니다."))
        self.assertEqual(self.payload(raw)["projectSignals"], [])
        data = json.loads(raw)
        self.assertEqual(data["projectSignals"], ["FEATURE_IMPLEMENTATION", "DEPLOYMENT"])
        self.assertEqual(data["technologies"], ["Spring", "Docker"])

    def test_hidden_and_quoted_actions_are_not_extracted(self):
        result = self.payload('<p>Spring</p><script>Docker로 서비스를 배포했습니다.</script><blockquote>프로젝트 API를 구현했습니다.</blockquote>')
        self.assertEqual(result, {"technologies": ["Spring"], "technologySignals": [], "projectSignals": []})

    def test_english_past_actions_require_context_and_exclude_plans(self):
        self.assertEqual(self.payload("Implemented a Spring API. Tested the service. Deployed the Docker application.")["projectSignals"],
                         ["FEATURE_IMPLEMENTATION", "TESTING", "DEPLOYMENT"])

    def test_spring_implementation_testing_and_docker_deployment_link_independently(self):
        result = self.payload("Spring으로 API 기능을 구현했습니다. Spring으로 단위 테스트를 작성했습니다. Docker로 서비스를 배포했습니다.")
        self.assertEqual(result, {
            "technologies": ["Spring", "Docker"],
            "technologySignals": [
                {"technology": "Spring", "signals": ["FEATURE_IMPLEMENTATION", "TESTING"]},
                {"technology": "Docker", "signals": ["DEPLOYMENT"]}],
            "projectSignals": ["FEATURE_IMPLEMENTATION", "TESTING", "DEPLOYMENT"]})

    def test_explicit_clauses_can_link_multiple_technologies_without_cross_assignment(self):
        for source in (
            "Spring으로 기능을 구현했고, Docker로 서비스를 배포했습니다.",
            "Spring으로 기능을 구현했고 Docker로 서비스를 배포했습니다.",
            "Implemented a Spring API, deployed the Docker service.",
        ):
            with self.subTest(source=source):
                self.assertEqual(self.payload(source)["technologySignals"], [
                    {"technology": "Spring", "signals": ["FEATURE_IMPLEMENTATION"]},
                    {"technology": "Docker", "signals": ["DEPLOYMENT"]}])

    def test_ambiguous_multiple_technologies_are_project_signals_only(self):
        for source in (
            "Spring과 Docker로 서비스를 배포했습니다.",
            "Spring, Docker로 서비스를 배포했습니다.",
            "Spring API를 Docker로 배포했습니다.",
        ):
            with self.subTest(source=source):
                result = self.payload(source)
                self.assertEqual(result["technologySignals"], [])
                self.assertEqual(result["projectSignals"], ["DEPLOYMENT"])

    def test_list_or_unattributed_action_does_not_link_across_sentence_or_clause(self):
        for source in (
            "사용 기술: Spring. 프로젝트 기능을 구현했습니다.",
            "사용 기술: Spring, 서비스 기능을 구현했습니다.",
            "Spring, 프로젝트 기능을 구현했습니다.",
        ):
            with self.subTest(source=source):
                result = self.payload(source)
                self.assertEqual(result["technologySignals"], [])
                self.assertEqual(result["projectSignals"], ["FEATURE_IMPLEMENTATION"])

    def test_negated_planned_or_learned_actions_never_create_links(self):
        for source in (
            "Spring으로 기능을 구현하지 않았습니다.",
            "Spring으로 API를 구현할 계획입니다.",
            "Spring 테스트와 Docker 배포를 학습했습니다.",
        ):
            with self.subTest(source=source):
                result = self.payload(source)
                self.assertEqual(result["technologySignals"], [])
                self.assertEqual(result["projectSignals"], [])

    def test_links_are_deduplicated_and_do_not_inherit_prior_technology(self):
        result = self.payload("Spring으로 API를 구현했습니다. Spring으로 API를 구현했습니다. 단위 테스트를 작성했습니다.")
        self.assertEqual(result["technologySignals"], [
            {"technology": "Spring", "signals": ["FEATURE_IMPLEMENTATION"]}])
        self.assertEqual(result["projectSignals"], ["FEATURE_IMPLEMENTATION", "TESTING"])

    def test_explicitly_excluded_technology_does_not_receive_the_performed_action(self):
        for source in ("Docker 없이 서비스를 배포했습니다.", "Deployed the service without Docker."):
            with self.subTest(source=source):
                result = self.payload(source)
                self.assertEqual(result["technologySignals"], [])
                self.assertEqual(result["projectSignals"], ["DEPLOYMENT"])
