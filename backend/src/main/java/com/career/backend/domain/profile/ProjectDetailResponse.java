package com.career.backend.domain.profile;

import java.time.OffsetDateTime;
import java.util.List;

public record ProjectDetailResponse(
        ProjectResponse project,
        List<EvaluationResponse> evaluations
) {

    public record EvaluationResponse(
            Long capabilityId,
            String capabilityName,
            int confirmedScore,
            SkillLevel level,
            OffsetDateTime evaluatedAt
    ) {

        public static EvaluationResponse from(UserSkillEvaluation evaluation) {
            return new EvaluationResponse(
                    evaluation.getCapability().getId(),
                    evaluation.getCapability().getName(),
                    evaluation.getConfirmedScore(),
                    evaluation.getLevel(),
                    evaluation.getEvaluatedAt()
            );
        }
    }
}
