package com.career.backend.api.posting;

import com.career.backend.TestFixtures;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** H2 checks API behaviour; PostgreSQL triggers are covered by db/tests/04-external-pass-material.sql. */
@SpringBootTest
@Transactional
class ExternalPassMaterialControllerTest {
    @Autowired WebApplicationContext context;
    @Autowired JdbcTemplate jdbc;
    @Autowired jakarta.persistence.EntityManager entityManager;
    MockMvc mvc;

    @BeforeEach void setup() {
        TestFixtures.insertAnalyzedPosting(jdbc);
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }
    void collection(String status) {
        jdbc.update("""
                insert into external_data.company_collection(company_id,status,minimum_sample_size,attempt_count,
                    requested_at,started_at,completed_at,updated_at,error_code,error_message)
                values(1,?,5,1,current_timestamp,current_timestamp,current_timestamp,current_timestamp,?,?)
                """, status, "FAILED".equals(status) ? "SOURCE_UNAVAILABLE" : null, "internal stack trace");
    }
    void material(long id, long companyId, String source, String externalId, String family) {
        jdbc.update("""
                insert into external_data.pass_material(id,company_id,source_platform,external_record_id,
                    job_family,role_name,title,content,source_url,collected_at,updated_at)
                values(?,?,?,?,?,'백엔드','합격 후기','개발 프로젝트 경험','https://example.com/pass',current_timestamp,current_timestamp)
                """, id, companyId, source, externalId, family);
    }
    void link(long id, long postingId, long materialId) {
        link(id, postingId, materialId, "EXACT_ROLE");
    }
    void link(long id, long postingId, long materialId, String relation) {
        jdbc.update("insert into external_data.posting_pass_material(id,posting_id,material_id,relation_type,linked_at) values(?,?,?,?,current_timestamp)", id, postingId, materialId, relation);
    }
    @Test void returnsOnlyExplicitlyLinkedSameCompanyItSwMaterialsWithPagination() throws Exception {
        collection("INSUFFICIENT");
        material(1, 1, "source", "1", "IT_SW");
        material(2, 1, "source", "2", "IT_SW");
        material(3, 1, "source", "3", "IT_SW"); // same company but not linked
        link(1, 1, 1); link(2, 1, 2);
        mvc.perform(get("/api/postings/1/external-pass-materials").param("size", "1"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.companyId").value(1))
                .andExpect(jsonPath("$.collection.status").value("INSUFFICIENT"))
                .andExpect(jsonPath("$.materials.totalElements").value(2))
                .andExpect(jsonPath("$.materials.totalPages").value(2))
                .andExpect(jsonPath("$.materials.content", hasSize(1)))
                .andExpect(jsonPath("$.materials.content[0].materialId").value(2))
                .andExpect(jsonPath("$.materials.content[0].sourcePlatform").value("source"));
        mvc.perform(get("/api/postings/1/external-pass-materials").param("size", "1").param("page", "1"))
                .andExpect(jsonPath("$.materials.content[0].materialId").value(1));
    }
    @Test void defensivelyFiltersForeignCompaniesAndNonItSwEvenIfBadLinksExist() throws Exception {
        collection("READY");
        material(1, 2, "source", "1", "IT_SW");
        material(2, 1, "source", "2", "SALES");
        link(1, 1, 1); link(2, 1, 2); // H2 has no PostgreSQL migration triggers/checks.
        mvc.perform(get("/api/postings/1/external-pass-materials"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.materials.content", hasSize(0)))
                .andExpect(jsonPath("$.materials.totalElements").value(0));
    }
    @Test void missingCollectionIsNotRequestedAndGetDoesNotCreateIt() throws Exception {
        mvc.perform(get("/api/postings/1/external-pass-materials"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.collection").value(nullValue()))
                .andExpect(jsonPath("$.materials.content", hasSize(0)));
        assertEquals(0, jdbc.queryForObject("select count(*) from external_data.company_collection", Integer.class));
    }
    @Test void returnsEveryPipelineStatusAndDoesNotExposeInternalErrorMessage() throws Exception {
        collection("PENDING");
        for (String state : new String[]{"PENDING", "RUNNING", "READY", "INSUFFICIENT", "FAILED"}) {
            jdbc.update("update external_data.company_collection set status=?, error_code='SOURCE_UNAVAILABLE' where company_id=1", state);
            // Each real HTTP request has a fresh persistence context; the test shares one transaction.
            entityManager.clear();
            mvc.perform(get("/api/postings/1/external-pass-materials"))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.collection.status").value(state))
                    .andExpect(jsonPath("$.collection.errorMessage").doesNotExist());
        }
    }
    @Test void missingPostingIs404AndInvalidPageSizeOrIdIs400() throws Exception {
        mvc.perform(get("/api/postings/999/external-pass-materials")).andExpect(status().isNotFound());
        mvc.perform(get("/api/postings/0/external-pass-materials")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/postings/1/external-pass-materials").param("page", "-1")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/postings/1/external-pass-materials").param("size", "101")).andExpect(status().isBadRequest());
    }
    @Test void sourceAndExternalIdAreUniqueButOtherPlatformsMayReuseId() {
        material(1, 1, "source", "1", "IT_SW");
        material(2, 1, "another", "1", "IT_SW");
        assertThrows(DataIntegrityViolationException.class, () -> material(3, 1, "source", "1", "IT_SW"));
    }
    @Test void linkIsUniquePerPostingAndOneMaterialCanServeMultipleSameCompanyPostings() {
        collection("READY");
        material(1, 1, "source", "1", "IT_SW");
        link(1, 1, 1); link(2, 2, 1);
        assertThrows(DataIntegrityViolationException.class, () -> link(3, 1, 1));
    }
    @Test void sameCompanyPostingsShareOneCollectionButHaveIndependentRelations() throws Exception {
        collection("READY");
        material(1, 1, "source", "1", "IT_SW");
        link(1, 1, 1, "EXACT_ROLE");
        link(2, 2, 1, "SAME_IT_DOMAIN");
        for (long postingId : new long[]{1, 2}) {
            mvc.perform(get("/api/postings/{id}/external-pass-materials", postingId))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.collection.companyId").value(1))
                    .andExpect(jsonPath("$.collection.status").value("READY"))
                    .andExpect(jsonPath("$.collection.attemptCount").value(1))
                    .andExpect(jsonPath("$.materials.content[0].materialId").value(1))
                    .andExpect(jsonPath("$.materials.content[0].relationType")
                            .value(postingId == 1 ? "EXACT_ROLE" : "SAME_IT_DOMAIN"));
        }
        assertEquals(1, jdbc.queryForObject("select count(*) from external_data.company_collection", Integer.class));
        assertEquals(1, jdbc.queryForObject("select count(*) from external_data.pass_material", Integer.class));
        // A newly encountered posting from the same company must not create/requeue the company task.
        assertThrows(DataIntegrityViolationException.class, () -> jdbc.update("""
                insert into external_data.company_collection(company_id,status,minimum_sample_size,attempt_count,requested_at,updated_at)
                select company_id,'PENDING',5,0,current_timestamp,current_timestamp from public.posting where id=2
                """));
        assertEquals("READY", jdbc.queryForObject("select status from external_data.company_collection where company_id=1", String.class));
    }
    @Test void excludedRelationDoesNotAffectOtherPostingsAndIsNotCounted() throws Exception {
        collection("READY");
        material(1, 1, "source", "1", "IT_SW");
        material(2, 1, "source", "2", "IT_SW");
        link(1, 1, 1, "EXCLUDED");
        link(2, 2, 1, "SAME_JOB_FAMILY");
        link(3, 1, 2, "EXACT_ROLE");
        mvc.perform(get("/api/postings/1/external-pass-materials").param("size", "1"))
                .andExpect(jsonPath("$.materials.totalElements").value(1))
                .andExpect(jsonPath("$.materials.content", hasSize(1)))
                .andExpect(jsonPath("$.materials.content[0].materialId").value(2));
        mvc.perform(get("/api/postings/2/external-pass-materials"))
                .andExpect(jsonPath("$.materials.totalElements").value(1))
                .andExpect(jsonPath("$.materials.content[0].relationType").value("SAME_JOB_FAMILY"));
        assertEquals("EXCLUDED", jdbc.queryForObject("select relation_type from external_data.posting_pass_material where id=1", String.class));
    }
    @Test void externalReadLeavesOriginalExtractionAndInternalComparisonsUntouched() throws Exception {
        var before = jdbc.queryForList("select * from public.requirement order by id");
        collection("PENDING");
        mvc.perform(get("/api/postings/1/external-pass-materials")).andExpect(status().isOk());
        assertEquals(before, jdbc.queryForList("select * from public.requirement order by id"));
        assertEquals(0, jdbc.queryForObject("select count(*) from profile.successful_application", Integer.class));
    }

    @Test void returnsStructuredTechnologySignalsAsExistingContentString() throws Exception {
        collection("READY");
        material(1, 1, "linkareer", "101", "IT_SW");
        link(1, 1, 1);
        String content = """
                {"technologies":["Spring","Docker"],"technologySignals":[{"technology":"Spring","signals":["FEATURE_IMPLEMENTATION","TESTING"]},{"technology":"Docker","signals":["DEPLOYMENT"]}],"projectSignals":["FEATURE_IMPLEMENTATION","TESTING","DEPLOYMENT"]}
                """.trim();
        jdbc.update("update external_data.pass_material set content=? where id=1", content);
        mvc.perform(get("/api/postings/1/external-pass-materials"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.materials.content[0].content").value(content));
    }
}
