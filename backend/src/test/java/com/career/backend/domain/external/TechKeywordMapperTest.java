package com.career.backend.domain.external;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static com.career.backend.domain.external.TechKeywordMapper.Entry;

class TechKeywordMapperTest {
    @Test void namesWinOverAliasesRegardlessOfDictionaryOrder() {
        var mapper = new TechKeywordMapper(List.of(
                new Entry(10L, "Spring", List.of("Spring Boot")),
                new Entry(11L, "Spring Boot", List.of("spring"))));
        assertEquals(10L, mapper.match(" SPRING ").orElseThrow().id());
        assertEquals(11L, mapper.match("spring boot").orElseThrow().id());
    }

    @Test void aliasesMustBeDeclaredAndOnlyCaseAndEdgeWhitespaceAreNormalized() {
        var mapper = new TechKeywordMapper(List.of(new Entry(10L, "Spring", List.of("Spring Boot", "스프링"))));
        assertEquals(10L, mapper.match(" Spring Boot ").orElseThrow().id());
        assertEquals(10L, mapper.match("스프링").orElseThrow().id());
        assertTrue(mapper.match("SpringBoot").isEmpty());
        assertTrue(mapper.match("Spring-Boot").isEmpty());
        assertTrue(mapper.match("Spring  Boot").isEmpty());
        assertTrue(mapper.match("Ｓｐｒｉｎｇ").isEmpty());
        assertTrue(new TechKeywordMapper(List.of(new Entry(10L, "Spring", List.of())))
                .match("Spring Boot").isEmpty());
    }

    @Test void aliasCollisionsAreUnmappedInsteadOfPickingAnArbitraryId() {
        var mapper = new TechKeywordMapper(List.of(
                new Entry(10L, "Spring", List.of("framework")),
                new Entry(11L, "Django", List.of("FRAMEWORK"))));
        assertTrue(mapper.match("framework").isEmpty());
    }

    @Test void normalizedNameCollisionsCannotFallBackToAnAlias() {
        var mapper = new TechKeywordMapper(List.of(
                new Entry(10L, "Spring", null), new Entry(11L, "spring", List.of()),
                new Entry(12L, "Other", List.of("SPRING"))));
        assertTrue(mapper.match("spring").isEmpty());
        assertTrue(mapper.match(null).isEmpty());
        assertTrue(mapper.match(" ").isEmpty());
    }
}
