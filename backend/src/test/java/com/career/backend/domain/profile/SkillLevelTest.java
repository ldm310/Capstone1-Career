package com.career.backend.domain.profile;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SkillLevelTest {

    @Test
    void 점수_구간마다_LV가_정해진다() {
        assertEquals(SkillLevel.LV0, SkillLevel.fromScore(0));
        assertEquals(SkillLevel.LV0, SkillLevel.fromScore(29));
        assertEquals(SkillLevel.LV1, SkillLevel.fromScore(30));
        assertEquals(SkillLevel.LV1, SkillLevel.fromScore(59));
        assertEquals(SkillLevel.LV2, SkillLevel.fromScore(60));
        assertEquals(SkillLevel.LV2, SkillLevel.fromScore(84));
        assertEquals(SkillLevel.LV3, SkillLevel.fromScore(85));
        assertEquals(SkillLevel.LV3, SkillLevel.fromScore(100));
    }

    @Test
    void 범위를_벗어난_점수는_거부한다() {
        assertThrows(IllegalArgumentException.class, () -> SkillLevel.fromScore(-1));
        assertThrows(IllegalArgumentException.class, () -> SkillLevel.fromScore(101));
    }
}
