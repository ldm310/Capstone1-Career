package com.career.backend.api.posting;

import com.career.backend.TestFixtures;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@Transactional
class ExternalPassKeywordControllerTest {
    @Autowired WebApplicationContext context;
    @Autowired JdbcTemplate jdbc;
    MockMvc mvc;

    @BeforeEach void setup() {
        TestFixtures.insertAnalyzedPosting(jdbc);
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
        tech(10, "Spring", "Spring Boot", "스프링");
        tech(15, "Docker", "도커");
        tech(21, "Kubernetes", "K8s");
        tech(40, "SignalOnly");
        jdbc.update("update job.requirement_tech set tech_id=10 where id=1");
        jdbc.update("update job.requirement_tech set tech_id=15 where id=2");
        jdbc.update("insert into job.requirement_tech(id,requirement_id,tech_id,written_name) values(3,2,10,'스프링')");
        jdbc.update("insert into job.requirement_tech(id,requirement_id,tech_id,written_name) values(4,3,10,'Spring')");
        jdbc.update("insert into job.unit_item(id,unit_id,category,seq,text,quote) values(4,1,'업무',1,'운영','운영')");
        jdbc.update("insert into job.requirement(id,item_id,capability_id,other_name,relation) values(4,4,2,'','모두')");
        jdbc.update("insert into job.requirement_tech(id,requirement_id,tech_id,written_name) values(5,4,21,'Kubernetes')");
    }

    void tech(long id, String name, String... aliases) {
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("insert into job.tech(id,name,aliases) values(?,?,?)");
            statement.setLong(1, id); statement.setString(2, name);
            statement.setArray(3, connection.createArrayOf("VARCHAR", aliases));
            return statement;
        });
    }

    void material(long id, long company, String relation, String content) {
        jdbc.update("""
                insert into external_data.pass_material(id,company_id,source_platform,external_record_id,job_family,
                    role_name,title,content,source_url,collected_at,updated_at)
                values(?,?,'linkareer',?,'IT_SW','backend','외부 자료',?,'https://example.com',current_timestamp,current_timestamp)
                """, id, company, Long.toString(id), content);
        jdbc.update("insert into external_data.posting_pass_material(id,posting_id,material_id,relation_type,linked_at) values(?,1,?,?,current_timestamp)", id, id, relation);
    }

    @Test void comparesByIdDeduplicatesPerMaterialAndPlacesRequiredBeforePreferred() throws Exception {
        material(1, 1, "EXACT_ROLE", """
                {"technologies":["Spring"," spring ","Spring Boot","Docker","K8s"," mystery ","mystery"],
                 "technologySignals":[{"technology":"SignalOnly","signals":["TESTING"]}],"projectSignals":["SignalOnly"]}
                """);
        material(2, 1, "SAME_JOB_FAMILY", "{\"technologies\":[\"스프링\",\"docker\",\"Spring Boot\"]}");
        material(3, 1, "EXCLUDED", "{\"technologies\":[\"Spring\",\"excluded-unknown\"]}");
        material(4, 2, "EXACT_ROLE", "{\"technologies\":[\"Spring\",\"foreign-unknown\"]}");
        mvc.perform(get("/api/postings/1/external-pass-keywords"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.sourceMaterialCount").value(2))
                .andExpect(jsonPath("$.requiredOverlap", hasSize(1)))
                .andExpect(jsonPath("$.requiredOverlap[0].techId").value(10))
                .andExpect(jsonPath("$.requiredOverlap[0].name").value("Spring"))
                .andExpect(jsonPath("$.requiredOverlap[0].materialCount").value(2))
                .andExpect(jsonPath("$.preferredOverlap", hasSize(1)))
                .andExpect(jsonPath("$.preferredOverlap[0].techId").value(15))
                .andExpect(jsonPath("$.preferredOverlap[0].materialCount").value(2))
                .andExpect(jsonPath("$.externalOnly", hasSize(1)))
                .andExpect(jsonPath("$.externalOnly[0].techId").value(21))
                .andExpect(jsonPath("$.externalOnly[0].materialCount").value(1))
                .andExpect(jsonPath("$.unmappedKeywords", contains("mystery")));
    }

    @Test void exactNameWinsOverExistingAliasAndUndeclaredKeywordsStayUnmapped() throws Exception {
        tech(11, "Spring Boot");
        material(1, 1, "EXACT_ROLE", "{\"technologies\":[\" spring boot \",\"SpringBoot\",\"Spring-Boot\",\"Spring  Boot\"]}");
        mvc.perform(get("/api/postings/1/external-pass-keywords"))
                .andExpect(jsonPath("$.requiredOverlap", hasSize(0)))
                .andExpect(jsonPath("$.externalOnly[0].techId").value(11))
                .andExpect(jsonPath("$.externalOnly[0].materialCount").value(1))
                .andExpect(jsonPath("$.unmappedKeywords", hasSize(3)));
    }

    @Test void emptyOrExcludedSourcesReturnZeroAndEmptyArrays() throws Exception {
        material(1, 1, "EXCLUDED", "{\"technologies\":[\"Spring\"]}");
        for (long id : new long[]{1, 2}) {
            mvc.perform(get("/api/postings/{id}/external-pass-keywords", id))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.sourceMaterialCount").value(0))
                    .andExpect(jsonPath("$.requiredOverlap", hasSize(0)))
                    .andExpect(jsonPath("$.preferredOverlap", hasSize(0)))
                    .andExpect(jsonPath("$.externalOnly", hasSize(0)))
                    .andExpect(jsonPath("$.unmappedKeywords", hasSize(0)));
        }
    }

    @Test void legacyMalformedMissingAndNonStringValuesAreNotRetokenized() throws Exception {
        material(1, 1, "EXACT_ROLE", "Spring Docker 원문 요약");
        material(2, 1, "EXACT_ROLE", "{broken");
        material(3, 1, "EXACT_ROLE", "{\"technologySignals\":[{\"technology\":\"Spring\"}]}");
        material(4, 1, "EXACT_ROLE", "{\"technologies\":[null,10,{},\" \"]}");
        mvc.perform(get("/api/postings/1/external-pass-keywords"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.sourceMaterialCount").value(4))
                .andExpect(jsonPath("$.requiredOverlap", hasSize(0)))
                .andExpect(jsonPath("$.preferredOverlap", hasSize(0)))
                .andExpect(jsonPath("$.externalOnly", hasSize(0)))
                .andExpect(jsonPath("$.unmappedKeywords", hasSize(0)));
    }

    @Test void onlyCurrentExtractionIdsAreUsedAndNullTechIdIsNeverResolvedFromWrittenName() throws Exception {
        jdbc.update("update job.requirement_tech set tech_id=null, written_name='Docker' where id=2");
        jdbc.update("""
                insert into job.extraction_run(id,posting_id,model,dict_version,is_current,run_at)
                values(2,1,'old','test',false,current_timestamp)
                """);
        jdbc.update("insert into job.recruit_unit(id,run_id,seq,name,is_it,career,years_text) values(3,2,1,'과거',true,'신입','')");
        jdbc.update("insert into job.unit_item(id,unit_id,category,seq,text,quote) values(5,3,'필수',1,'과거','과거')");
        jdbc.update("insert into job.requirement(id,item_id,capability_id,other_name,relation) values(5,5,2,'','모두')");
        jdbc.update("insert into job.requirement_tech(id,requirement_id,tech_id,written_name) values(6,5,15,'Docker')");
        material(1, 1, "EXACT_ROLE", "{\"technologies\":[\"Docker\"]}");
        mvc.perform(get("/api/postings/1/external-pass-keywords"))
                .andExpect(jsonPath("$.requiredOverlap", hasSize(0)))
                .andExpect(jsonPath("$.preferredOverlap", hasSize(0)))
                .andExpect(jsonPath("$.externalOnly[0].techId").value(15));
    }

    @Test void keywordQueryDoesNotModifySourcesDictionaryOrOriginalPostingOutput() throws Exception {
        material(1, 1, "EXACT_ROLE", "{\"technologies\":[\"Spring Boot\",\"new-tech\"],\"projectSignals\":[\"DEPLOYMENT\"]}");
        var beforeMaterials = jdbc.queryForList("select id,content from external_data.pass_material order by id");
        var beforeRequirements = jdbc.queryForList("select * from job.requirement_tech order by id");
        int dictionaryCount = jdbc.queryForObject("select count(*) from job.tech", Integer.class);
        mvc.perform(get("/api/postings/1/external-pass-keywords")).andExpect(status().isOk());
        assertEquals(beforeMaterials, jdbc.queryForList("select id,content from external_data.pass_material order by id"));
        assertEquals(beforeRequirements, jdbc.queryForList("select * from job.requirement_tech order by id"));
        assertEquals(dictionaryCount, jdbc.queryForObject("select count(*) from job.tech", Integer.class));
    }

    @Test void keywordQueryHasNoTwentyMaterialPageLimit() throws Exception {
        for (int id = 1; id <= 21; id++) material(id, 1, "EXACT_ROLE", "{\"technologies\":[\"Spring\"]}");
        mvc.perform(get("/api/postings/1/external-pass-keywords"))
                .andExpect(jsonPath("$.sourceMaterialCount").value(21))
                .andExpect(jsonPath("$.requiredOverlap[0].materialCount").value(21));
    }

    @Test void missingPostingIs404AndNonpositiveIdIs400() throws Exception {
        mvc.perform(get("/api/postings/999/external-pass-keywords")).andExpect(status().isNotFound());
        mvc.perform(get("/api/postings/0/external-pass-keywords")).andExpect(status().isBadRequest());
    }
}
