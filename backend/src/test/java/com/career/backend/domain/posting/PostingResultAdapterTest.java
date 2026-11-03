package com.career.backend.domain.posting;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static com.career.backend.domain.posting.PostingResultAdapter.*;

class PostingResultAdapterTest {
    private final PostingResultAdapter adapter = new PostingResultAdapter();
    private Item item(String text, Req... reqs) { return new Item(text, List.of(reqs), text); }
    private Req req(String capability, String... techs) { return new Req(capability, "", List.of(techs), "모두"); }
    private Extraction input(List<Item> required, List<Item> preferred, List<Item> duties, List<Item> other) {
        return new Extraction(List.of(new ExtractedPosition("서버", true, "경력", "3년 이상",
                required, preferred, duties, other)), List.of("분석 제외"), "원본");
    }
    @Test void separatesConditionsPreservesMixedSkillsCategoriesDuplicatesAndOriginal() {
        var mysql = item("MySQL 경력 3년 이상", req("관계형 DB", "MySQL", "MySQL"));
        var source = input(List.of(mysql, mysql, item("백엔드 경력 3년 이상"),
                        item("학사 이상", req("학력"))),
                List.of(item("Docker 우대", req("컨테이너", "Docker"))),
                List.of(item("API 개발", req("API 설계"))),
                List.of(item("GitHub", req("버전 관리", "GitHub"))));
        String before = source.toString();
        var result = adapter.adapt(source, Map.of("관계형 DB", 1L)).getFirst();
        assertEquals(1, result.requiredSkills().size());
        assertEquals(List.of("MySQL"), result.requiredSkills().getFirst().techs());
        assertEquals(3, result.requiredConditions().size());
        assertTrue(result.requiredConditions().stream().anyMatch(c -> c.type() == RequiredConditionRules.Type.CAREER_YEARS));
        assertEquals("컨테이너", result.preferredSkills().getFirst().capability());
        assertEquals("API 설계", result.dutySkills().getFirst().capability());
        assertEquals("버전 관리", result.environmentSkills().getFirst().capability());
        assertEquals(List.of("분석 제외"), result.skipped());
        assertEquals(before, source.toString());
    }
    @Test void nullFieldsBecomeEmptyArrays() {
        var result = adapter.adapt(input(null, null, null, null), Map.of()).getFirst();
        assertEquals(List.of(), result.requiredSkills()); assertEquals(List.of(), result.requiredConditions());
        assertEquals(List.of(), result.preferredSkills()); assertEquals(List.of(), result.dutySkills());
        assertEquals(List.of(), result.environmentSkills());
        assertEquals(List.of(), adapter.adapt(new Extraction(null, null, null), Map.of()));
    }
    @Test void conditionRulesCoverAllRequestedKindsWithoutConfusingProgrammingLanguages() {
        assertEquals(List.of(RequiredConditionRules.Type.LANGUAGE), RequiredConditionRules.detect("TOEIC 800점"));
        assertTrue(RequiredConditionRules.detect("컴퓨터공학 전공 학사").contains(RequiredConditionRules.Type.MAJOR));
        assertTrue(RequiredConditionRules.detect("정보처리기사 자격증").contains(RequiredConditionRules.Type.CERTIFICATE));
        assertTrue(RequiredConditionRules.detect("병역필, 서울 근무 가능").contains(RequiredConditionRules.Type.EMPLOYMENT));
        assertTrue(RequiredConditionRules.detect("프로그래밍 언어 Java").isEmpty());
    }
}
