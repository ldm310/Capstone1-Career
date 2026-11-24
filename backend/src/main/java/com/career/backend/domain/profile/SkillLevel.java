package com.career.backend.domain.profile;

// 확정 역량 점수(0~100)를 사용자에게 보여줄 LV로 바꾼다.
// LV 평가 기준(LV1 기초 사용 → LV2 프로젝트 연결 → LV3 개선·검증)에 맞춘 임시 구간이다.
public enum SkillLevel {

    LV0(0, "근거 부족"),
    LV1(30, "기초 사용"),
    LV2(60, "프로젝트 적용"),
    LV3(85, "개선·검증");

    private final int minScore;
    private final String description;

    SkillLevel(int minScore, String description) {
        this.minScore = minScore;
        this.description = description;
    }

    public static SkillLevel fromScore(int score) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException(
                    "확정 역량 점수는 0~100 사이여야 합니다."
            );
        }

        SkillLevel result = LV0;

        for (SkillLevel level : values()) {
            if (score >= level.minScore) {
                result = level;
            }
        }

        return result;
    }

    public int getMinScore() {
        return minScore;
    }

    public String getDescription() {
        return description;
    }
}
