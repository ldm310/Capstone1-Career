package com.career.backend.domain.profile;

import java.time.OffsetDateTime;
import java.util.List;

public record UserCapabilityResponse(
        Long capabilityId,
        String capabilityName,
        String groupName,
        int bestScore,
        SkillLevel level,
        List<ProjectScoreResponse> projects
) {

    public record ProjectScoreResponse(
            Long projectId,
            String projectName,
            int score,
            SkillLevel level,
            OffsetDateTime evaluatedAt
    ) {
    }
}
