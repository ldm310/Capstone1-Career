package com.career.backend.domain.skill;

public enum SkillLevel {

    UNASSESSED(0),
    LV0(1),
    LV1(2),
    LV2(3),
    LV3(4),
    LV4(5),
    LV5(6);

    private final int score;

    SkillLevel(int score) {
        this.score = score;
    }

    public int getScore() {
        return score;
    }
}