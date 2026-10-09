package com.career.backend.domain.application;

import com.career.backend.domain.study.StudyBand;

public record StudyMatchCandidate(
        Long applicationId,
        Long userId,
        String nickname,
        StudyBand studyBand,
        Double averageSkillScore
) {
}