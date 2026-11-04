import json
import unittest
from external_pass_crawler.privacy import technical_summary


class PrivacyTests(unittest.TestCase):
    def payload(self, source):
        return json.loads(technical_summary(source))

    def test_basic_use_does_not_imply_implementation_testing_or_deployment(self):
        for source in ("Spring과 Docker를 사용한 경험이 있습니다.", "Spring과 Docker 사용 경험이 있습니다.", "Spring과 Docker를 사용해 본 경험이 있습니다."):
            with self.subTest(source=source):
                self.assertEqual(self.payload(source), {"technologies": ["Spring", "Docker"], "projectSignals": ["BASIC_USE"]})

    def test_technologies_alone_do_not_infer_any_signal(self):
        self.assertEqual(self.payload("Spring Docker"), {"technologies": ["Spring", "Docker"], "projectSignals": []})

    def test_explicit_implementation_testing_and_deployment_are_distinct(self):
        result = self.payload("Spring으로 기능을 구현했습니다. 단위 테스트를 작성했습니다. Docker로 서비스를 배포했습니다.")
        self.assertEqual(result, {"technologies": ["Spring", "Docker"],
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
        self.assertEqual(set(data), {"technologies", "projectSignals"})
        for forbidden in ("가상작성자", "가상학교", "010-", "fictional@", "비밀프로젝트", "구현했습니다", "LV", "score", "quote"):
            self.assertNotIn(forbidden, raw)

    def test_empty_input_produces_two_empty_arrays(self):
        self.assertEqual(self.payload(""), {"technologies": [], "projectSignals": []})

    def test_signals_are_unique_and_order_is_deterministic(self):
        raw = technical_summary("Spring으로 API를 구현했습니다. Docker로 서비스를 배포했습니다. Spring으로 API를 구현했습니다.")
        self.assertEqual(raw, technical_summary("Spring으로 API를 구현했습니다. Docker로 서비스를 배포했습니다. Spring으로 API를 구현했습니다."))
        self.assertEqual(self.payload(raw)["projectSignals"], [])
        data = json.loads(raw)
        self.assertEqual(data["projectSignals"], ["FEATURE_IMPLEMENTATION", "DEPLOYMENT"])
        self.assertEqual(data["technologies"], ["Spring", "Docker"])

    def test_hidden_and_quoted_actions_are_not_extracted(self):
        result = self.payload('<p>Spring</p><script>Docker로 서비스를 배포했습니다.</script><blockquote>프로젝트 API를 구현했습니다.</blockquote>')
        self.assertEqual(result, {"technologies": ["Spring"], "projectSignals": []})

    def test_english_past_actions_require_context_and_exclude_plans(self):
        self.assertEqual(self.payload("Implemented a Spring API. Tested the service. Deployed the Docker application.")["projectSignals"],
                         ["FEATURE_IMPLEMENTATION", "TESTING", "DEPLOYMENT"])
