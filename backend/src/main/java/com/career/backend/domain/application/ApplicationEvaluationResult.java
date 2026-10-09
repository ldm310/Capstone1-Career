package com.career.backend.domain.application;

import com.career.backend.domain.study.StudyBand;

public record ApplicationEvaluationResult(
        Long applicationId,
        int requiredSkillCount,
        double averageSkillScore,
        StudyBand studyBand
) {
}