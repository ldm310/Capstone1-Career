package com.career.backend.domain.study;

import com.career.backend.domain.skill.SkillLevel;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StudyBandCalculatorTest {

    @Test
    void 낮은_레벨은_LOW로_분류한다() {
        List<SkillLevel> levels = List.of(
                SkillLevel.LV0,
                SkillLevel.LV1,
                SkillLevel.UNASSESSED
        );

        StudyBand result = StudyBandCalculator.calculate(levels);

        assertEquals(StudyBand.LOW, result);
    }

    @Test
    void 중간_레벨은_MIDDLE로_분류한다() {
        List<SkillLevel> levels = List.of(
                SkillLevel.LV2,
                SkillLevel.LV3
        );

        StudyBand result = StudyBandCalculator.calculate(levels);

        assertEquals(StudyBand.MIDDLE, result);
    }

    @Test
    void 높은_레벨은_HIGH로_분류한다() {
        List<SkillLevel> levels = List.of(
                SkillLevel.LV4,
                SkillLevel.LV5
        );

        StudyBand result = StudyBandCalculator.calculate(levels);

        assertEquals(StudyBand.HIGH, result);
    }

    @Test
    void 기술_목록이_비어있으면_예외가_발생한다() {
        assertThrows(
                IllegalArgumentException.class,
                () -> StudyBandCalculator.calculate(List.of())
        );
    }
}