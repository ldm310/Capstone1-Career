package com.career.backend.api.posting;

import com.career.backend.TestFixtures;
import com.career.backend.domain.posting.SkillCategoryService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;
import tools.jackson.databind.ObjectMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@Transactional
class SkillCategoryControllerTest {
    @Autowired WebApplicationContext context;
    @Autowired JdbcTemplate jdbc;
    @Autowired SkillCategoryService categories;
    MockMvc mvc;

    @BeforeEach void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
        TestFixtures.insertAnalyzedPosting(jdbc);
    }

    @Test void catalogSeparatesTechnicalCategoriesAndReferences() throws Exception {
        mvc.perform(get("/api/skill-categories"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.categories", hasSize(10)))
                .andExpect(jsonPath("$.categories[4].code").value("O"))
                .andExpect(jsonPath("$.categories[4].sentenceCount").value(1127))
                .andExpect(jsonPath("$.otherSentences").value(880))
                .andExpect(jsonPath("$.excludedSentences").value(804))
                .andExpect(jsonPath("$.unclassifiedSentences").value(0))
                .andExpect(jsonPath("$.certificateReferenceSentences").value(101))
                .andExpect(jsonPath("$.levelScoringEnabled").value(false));
    }

    @Test void excludedUnknownAndOtherHaveDifferentMeaning() {
        assertThat(categories.classify("문제 해결 능력과 원활한 의사소통 및 협업 능력").status()).isEqualTo("EXCLUDED");
        assertThat(categories.classify("아직 검토하지 않은 새로운 요건 20261119").status()).isEqualTo("UNCLASSIFIED");
        var cloud = categories.classify("포인트 클라우드(PCD/PLY) 기반 메싱, RANSAC, 정합 알고리즘 구현 경험");
        assertThat(cloud.status()).isEqualTo("CLASSIFIED");
        assertThat(cloud.categoryCodes()).contains("OTHER").doesNotContain("O");
        var actual = categories.classify("운영 중인 시스템을 무중단으로 새 구조로 이관한 경험");
        assertThat(actual.categoryCodes()).containsExactly("O");
        assertThat(categories.classify("  Python\n등\t프로그래밍 언어를 활용한 개발 가능자  ").categoryCodes()).containsExactly("L");
    }

    @Test void currentPostingMatchesReviewedTextWithoutChangingSource() throws Exception {
        jdbc.update("update public.unit_item set text=? where category='필수'", "외부 시스템 연동과 장애 해결 경험");
        var result = mvc.perform(get("/api/postings/1/skill-categories"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        var json = new ObjectMapper().readTree(result);
        var item = json.get("recruitUnits").get(0).get("items").get(0);
        assertThat(item.get("assignment").get("categoryCodes").toString()).isEqualTo("[\"B\",\"O\"]");
        mvc.perform(get("/api/postings/1"))
                .andExpect(jsonPath("$.analysis.recruitUnits[0].items[0].requirements[0].capabilityName").value("관계형 DB"));
        mvc.perform(get("/api/postings/2/skill-categories"))
                .andExpect(status().isNotFound());
        jdbc.update("update public.posting set status='진행' where id=2");
        context.getBean(jakarta.persistence.EntityManager.class).clear();
        // Reopening a posting without target-role extraction does not make it public.
        mvc.perform(get("/api/postings/2/skill-categories"))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/postings/999/skill-categories")).andExpect(status().isNotFound());
    }

    @Test void swaggerContainsBothCategoryRoutes() throws Exception {
        mvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/skill-categories'].get").exists())
                .andExpect(jsonPath("$.paths['/api/postings/{postingId}/skill-categories'].get").exists());
    }
}
