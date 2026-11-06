package com.career.backend.domain.posting;

import com.career.backend.TestFixtures;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import java.time.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Transactional
class CapabilityComparisonTest {
    @Autowired JdbcTemplate jdbc;
    @Autowired CapabilityComparisonService service;
    @BeforeEach void setup() {
        TestFixtures.insertAnalyzedPosting(jdbc);
        user(100);
        jdbc.update("insert into profile.comparison_target(unit_id, role_group, career_band) values(1, 'BACKEND', 'JUNIOR')");
    }
    void user(long id) {
        jdbc.update("insert into profile.app_user(user_id,email,name,created_at,updated_at) values(?,?,'사용자',current_timestamp,current_timestamp)", id, id + "@test.local");
    }
    void applicant(long id, long company) {
        user(id);
        jdbc.update("insert into profile.successful_application(user_id,company_id,posting_id,role_group,career_band,stage,verified,accepted_at) values(?,?,2,'BACKEND','JUNIOR','DOCUMENT_PASSED',true,?)",
                id, company, LocalDate.now(ZoneId.of("Asia/Seoul")));
        jdbc.update("insert into profile.project(project_id,user_id,project_name,created_at,updated_at) values(?,?,'Evidence',current_timestamp,current_timestamp)", id, id);
        jdbc.update("insert into profile.user_skill_evaluation(project_id,capability_id,confirmed_score,evaluated_at) values(?,1,70,current_timestamp)", id);
    }
    ApplicantReferenceService.Reference reference() { return service.compare(1L, 100L).positions().getFirst().reference(); }
    @Test void selectsCompanyAndAggregatesStoredEvaluations() {
        for (long id = 1; id <= 5; id++) applicant(id, 1);
        var ref = reference();
        assertEquals(ApplicantReferenceService.ReferenceType.SAME_COMPANY_SIMILAR_ROLE, ref.referenceType());
        assertEquals(5, ref.sampleSize());
        var stats = ref.capabilities().getFirst();
        assertEquals(5, stats.holderCount()); assertEquals(1.0, stats.holderRate()); assertEquals(2.0, stats.medianLevel());
        jdbc.update("insert into profile.project(project_id,user_id,project_name,created_at,updated_at) values(99,1,'중복 근거',current_timestamp,current_timestamp)");
        jdbc.update("insert into profile.user_skill_evaluation(project_id,capability_id,confirmed_score,evaluated_at) values(99,1,90,current_timestamp)");
        assertEquals(5, reference().capabilities().getFirst().holderCount());
        assertEquals(2.0, reference().capabilities().getFirst().medianLevel());
    }
    @Test void fallsBackToMarketWhenCompanySampleIsSmall() {
        for (long id = 1; id <= 5; id++) applicant(id, id == 1 ? 1 : 2);
        var ref = reference();
        assertEquals(ApplicantReferenceService.ReferenceType.MARKET_SAME_ROLE, ref.referenceType());
        assertEquals(1, ref.attempts().getFirst().sampleSize());
        assertTrue(ref.attempts().getFirst().insufficientData());
    }
    @Test void excludesUnverifiedOldFutureWrongRoleBandStageCurrentPostingAndSelf() {
        for (long id = 1; id <= 9; id++) applicant(id, 1);
        jdbc.update("update profile.successful_application set verified=false where user_id=1");
        jdbc.update("update profile.successful_application set accepted_at=? where user_id=2", LocalDate.now().minusYears(4));
        jdbc.update("update profile.successful_application set accepted_at=? where user_id=3", LocalDate.now().plusDays(2));
        jdbc.update("update profile.successful_application set role_group='FRONTEND' where user_id=4");
        jdbc.update("update profile.successful_application set career_band='SENIOR' where user_id=5");
        jdbc.update("update profile.successful_application set stage='APPLIED' where user_id=6");
        jdbc.update("update profile.successful_application set posting_id=1 where user_id=7");
        jdbc.update("update profile.successful_application set user_id=100 where user_id=8");
        var ref = reference();
        assertEquals(ApplicantReferenceService.ReferenceType.NONE, ref.referenceType());
        assertEquals(1, ref.attempts().getFirst().sampleSize());
        assertTrue(ref.insufficientData()); assertTrue(ref.capabilities().isEmpty());
    }
    @Test void missingTargetAndEmptySamplesAreExplicit() {
        assertEquals("INSUFFICIENT_SAMPLE", reference().reason());
        jdbc.update("delete from profile.comparison_target");
        assertEquals("COMPARISON_TARGET_MISSING", reference().reason());
    }
    @Test void apiReturnsEvidenceAndArraysWithoutChangingExtraction() throws Exception {
        var before = jdbc.queryForList("select * from public.requirement");
        var context = org.springframework.test.web.servlet.setup.MockMvcBuilders
                .standaloneSetup(new com.career.backend.api.posting.CapabilityComparisonController(service)).build();
        context.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .get("/api/postings/1/capability-comparison").param("userId", "100"))
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isOk())
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath("$.positions[0].posting.requiredSkills[0].capabilityId").value(1))
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath("$.positions[0].posting.dutySkills").isArray())
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath("$.positions[0].reference.referenceType").value("NONE"))
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath("$.userCapabilities").isArray());
        assertEquals(before, jdbc.queryForList("select * from public.requirement"));
    }
    @Test void preservesSkippedFromRawJson() {
        jdbc.update("update public.extraction_run set llm_output_raw = '{\"positions\":[],\"skipped\":[\"분석 제외 원문\"],\"notes\":\"유지\"}' format json where id=1");
        var before = jdbc.queryForObject("select llm_output_raw from public.extraction_run where id=1", String.class);
        var result = service.compare(1L, 100L);
        assertTrue(result.skippedAvailable());
        assertEquals(java.util.List.of("분석 제외 원문"), result.positions().getFirst().posting().skipped());
        assertEquals(before, jdbc.queryForObject("select llm_output_raw from public.extraction_run where id=1", String.class));
    }
}
