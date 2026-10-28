package com.career.backend.domain.profile;

// LLM 평가 결과 한 건: 표준화 사전의 능력 ID와 확정 점수(0~100)
public record EvaluationScore(
        Long capabilityId,
        int confirmedScore
) {
}
