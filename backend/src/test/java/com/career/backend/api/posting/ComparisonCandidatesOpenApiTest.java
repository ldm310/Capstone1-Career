package com.career.backend.api.posting;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
class ComparisonCandidatesOpenApiTest {
    @Autowired WebApplicationContext context;

    @Test void collectionStatusApiIsReadOnlyAndDocumentsErrorsAndFields() throws Exception {
        var response=MockMvcBuilders.webAppContextSetup(context).build().perform(get("/v3/api-docs"))
                .andExpect(status().isOk()).andReturn().getResponse();
        var document=new ObjectMapper().readTree(response.getContentAsString());
        var operation=document.path("paths").path("/api/postings/{postingId}/recruit-units/{recruitUnitId}/external-pass-collection-status").path("get");
        assertTrue(operation.path("description").asText().contains("읽기 전용"));
        for(String code:new String[]{"200","400","404","409"})assertTrue(operation.path("responses").has(code));
        var schema=resolve(document,operation.path("responses").path("200").path("content").path("application/json").path("schema"));
        for(String key:new String[]{"collectionStatus","highCandidateCount","materialCount","safeErrorCode","retryable","policyVersion"})
            assertTrue(schema.path("properties").has(key));
    }

    @Test void generatedOpenApiExposesDedicatedSchemaDescriptionsExamplesAndAllHttpStatuses() throws Exception {
        var mapper=new ObjectMapper();
        var response=MockMvcBuilders.webAppContextSetup(context).build().perform(get("/v3/api-docs"))
                .andExpect(status().isOk()).andReturn().getResponse();
        var document=mapper.readTree(response.getContentAsString());
        var operation=document.path("paths").path("/api/postings/{postingId}/recruit-units/{recruitUnitId}/comparison-candidates").path("get");
        assertFalse(operation.isMissingNode());
        assertTrue(operation.path("description").asText().contains("읽기 전용"));
        assertTrue(operation.path("description").asText().contains("LOW"));
        for(String code:new String[]{"200","400","404","409"})assertTrue(operation.path("responses").has(code));
        var content=operation.path("responses").path("200").path("content").path("application/json");
        assertEquals(4,content.path("examples").size());
        var low=content.path("examples").path("LOW 보조 비교").path("value");
        if(low.isString())low=mapper.readTree(low.asText());
        assertEquals("LOW",low.path("confidence").asText());
        assertTrue(low.path("candidates").get(0).path("requiredTechCoverage").isNull());
        var root=resolve(document,content.path("schema"));
        assertTrue(root.path("properties").has("recruitUnitId"));
        assertTrue(root.path("properties").has("appliedCriteria"));
        assertFalse(root.path("properties").has("units"));
        var candidate=resolve(document,root.path("properties").path("candidates").path("items"));
        assertTrue(candidate.path("properties").has("companyName"));
        assertTrue(candidate.path("properties").has("requiredTechCoverage"));
        assertTrue(candidate.path("properties").has("intersections"));
        assertFalse(candidate.path("properties").has("score"));
    }
    private JsonNode resolve(JsonNode document,JsonNode schema) {
        String ref=schema.path("$ref").asText("");
        return ref.isEmpty()?schema:document.path("components").path("schemas").path(ref.substring(ref.lastIndexOf('/')+1));
    }
}
