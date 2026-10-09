package com.career.backend.domain.study;

import com.career.backend.domain.skill.SkillLevel;

import java.util.List;

public final class StudyBandCalculator {

    private StudyBandCalculator() {
    }

    public static StudyBand calculate(List<SkillLevel> skillLevels) {
        double averageScore = calculateAverage(skillLevels); //평균으로 값니다 0~2 LOW, 2~4 MIDDLE, 4~6 HIGH

        if (averageScore <= 2.0) {
            return StudyBand.LOW;
        }

        if (averageScore <= 4.0) {
            return StudyBand.MIDDLE;
        }

        return StudyBand.HIGH;
    }

    public static double calculateAverage(List<SkillLevel> skillLevels) {
        if (skillLevels == null || skillLevels.isEmpty()) {
            throw new IllegalArgumentException("기술 레벨 목록은 비어 있을 수 없습니다.");
        }

        return skillLevels.stream()
                .mapToInt(SkillLevel::getScore)
                .average()
                .orElseThrow();
    }
}