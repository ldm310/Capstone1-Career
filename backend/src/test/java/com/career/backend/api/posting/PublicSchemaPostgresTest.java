package com.career.backend.api.posting;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Opt-in: fixtures are prepared by db/tests/test_public_schema_integration.py. */
@SpringBootTest
@EnabledIfEnvironmentVariable(named = "PUBLIC_SCHEMA_TEST_URL", matches = ".+")
@Transactional(readOnly = true)
class PublicSchemaPostgresTest {
    @Autowired JdbcTemplate jdbc;
    @Autowired WebApplicationContext context;

    @DynamicPropertySource
    static void isolatedPostgres(DynamicPropertyRegistry properties) {
        String url = System.getenv("PUBLIC_SCHEMA_TEST_URL");
        if (url == null || !url.matches("jdbc:postgresql://(127\\.0\\.0\\.1|localhost):[0-9]+/extcrawler_test[a-zA-Z0-9_]*")) {
            throw new IllegalArgumentException("An isolated local extcrawler_test database is required");
        }
        properties.add("spring.datasource.url", () -> url);
        properties.add("spring.datasource.username", () -> System.getenv("PUBLIC_SCHEMA_TEST_USER"));
        properties.add("spring.datasource.password", () -> System.getenv("PUBLIC_SCHEMA_TEST_PASSWORD"));
        properties.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
        properties.add("spring.jpa.hibernate.ddl-auto", () -> "validate");
        properties.add("spring.jpa.properties.hibernate.hbm2ddl.create_namespaces", () -> "false");
        properties.add("spring.sql.init.mode", () -> "never");
    }

    private Map<String, Object> snapshot() {
        Map<String, Object> result = new LinkedHashMap<>();
        for (String table : jdbc.queryForList("select tablename from pg_tables where schemaname='public' order by tablename", String.class)) {
            String quoted = "\"" + table.replace("\"", "\"\"") + "\"";
            result.put(table, jdbc.queryForMap("select count(*) as rows, md5(coalesce(string_agg(to_jsonb(t)::text, '' order by to_jsonb(t)::text), '')) as hash from public." + quoted + " t"));
        }
        return result;
    }

    @Test
    void readsPostingAndExternalKeywordsWithoutJobSchemaOrPublicWrites() throws Exception {
        assertEquals(0, jdbc.queryForObject("select count(*) from pg_namespace where nspname='job'", Integer.class));
        assertEquals("on", jdbc.queryForObject("show transaction_read_only", String.class));
        var before = snapshot();
        var mvc = MockMvcBuilders.webAppContextSetup(context).build();
        mvc.perform(get("/api/postings/1"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.postingId").value(1));
        mvc.perform(get("/api/postings/1/external-pass-materials"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.materials.totalElements").value(1));
        mvc.perform(get("/api/postings/1/external-pass-keywords"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requiredOverlap[0].techId").value(1))
                .andExpect(jsonPath("$.requiredOverlap[0].name").value("Java"));
        assertEquals(before, snapshot());
    }
}
