package com.career.backend.api.posting;

import com.career.backend.api.common.GlobalExceptionHandler;
import com.career.backend.domain.posting.similarity.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.context.properties.bind.*;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.support.TransactionTemplate;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Real GET/real selection in an explicitly isolated PostgreSQL READ ONLY transaction. */
@EnabledIfEnvironmentVariable(named="POSTING_SIMILARITY_TEST_URL",matches=".+")
class ComparisonCandidatesPostgresTest {
    JdbcTemplate jdbc;
    TransactionTemplate readOnly;
    MockMvc mvc;
    ComparisonCandidateMetadataRepository metadata;

    @BeforeEach void setup() throws Exception {
        String url=System.getenv("POSTING_SIMILARITY_TEST_URL");
        if(url==null||!url.matches("jdbc:postgresql://(127\\.0\\.0\\.1|localhost):[0-9]+/extcrawler_test_similarity_[a-z0-9]+"))
            throw new IllegalArgumentException("An isolated local similarity test database is required");
        var ds=new DriverManagerDataSource(url,System.getenv("POSTING_SIMILARITY_TEST_USER"),System.getenv("POSTING_SIMILARITY_TEST_PASSWORD"));
        ds.setDriverClassName("org.postgresql.Driver");jdbc=new JdbcTemplate(ds);
        var props=new Properties();
        try(var input=getClass().getResourceAsStream("/posting-similarity.properties")) {
            props.load(new InputStreamReader(Objects.requireNonNull(input),StandardCharsets.UTF_8));
        }
        Map<String,Object> values=new HashMap<>();props.forEach((k,v)->values.put(k.toString(),v));
        var binder=new Binder(new MapConfigurationPropertySource(values));
        var p=binder.bind("posting-similarity",Bindable.of(PostingSimilarityProperties.class)).orElseThrow(IllegalStateException::new);
        var taxonomy=binder.bind("posting-similarity.taxonomy",Bindable.of(RoleTaxonomy.class)).orElseThrow(IllegalStateException::new);
        var template=new NamedParameterJdbcTemplate(ds);
        var selection=new PostingCandidateSelectionService(new JdbcRecruitUnitFeatureRepository(template),
                new RecruitUnitRoleResolver(taxonomy),new KeywordPostingSimilarityScorer(),p);
        metadata=spy(new ComparisonCandidateMetadataRepository(template));
        var query=new ComparisonCandidatesQueryService(selection,metadata,taxonomy);
        mvc=MockMvcBuilders.standaloneSetup(new ComparisonCandidatesController(query)).setControllerAdvice(new GlobalExceptionHandler()).build();
        readOnly=new TransactionTemplate(new DataSourceTransactionManager(ds));readOnly.setReadOnly(true);
        readOnly.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_REPEATABLE_READ);
    }
    Map<String,Object> snapshot() {
        Map<String,Object> result=new TreeMap<>();
        for(String table:jdbc.queryForList("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",String.class)) {
            String name='"'+table.replace("\"","\"\"")+'"';
            result.put(table,jdbc.queryForMap("SELECT count(*) AS rows,md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) AS hash FROM public."+name+" t"));
        }
        result.put("sequences",jdbc.queryForList("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"));
        return result;
    }
    void unchanged(Checked assertions) {
        readOnly.executeWithoutResult(status->{
            assertEquals("on",jdbc.queryForObject("SHOW transaction_read_only",String.class));
            var before=snapshot();
            try { assertions.run(); } catch(Exception e) { throw new AssertionError(e); }
            assertEquals(before,snapshot());
            assertEquals("on",jdbc.queryForObject("SHOW transaction_read_only",String.class));
        });
    }
    interface Checked { void run() throws Exception; }

    @Test void selectedGetUsesRealServiceOneBatchAndLeavesEveryPublicTableAndSequenceUnchanged() {
        unchanged(()->{
            mvc.perform(get(ComparisonCandidatesControllerTest.ENDPOINT,1,11)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.selectionStatus").value("SELECTED"))
                    .andExpect(jsonPath("$.recruitUnitId").value(11))
                    .andExpect(jsonPath("$.candidates[0].postingId").value(3))
                    .andExpect(jsonPath("$.candidates[0].recruitUnitId").value(31))
                    .andExpect(jsonPath("$.candidates[0].companyName").value("fixture-other-a"))
                    .andExpect(jsonPath("$.candidates[0].postingTitle").value("Mixed posting fixture"))
                    .andExpect(jsonPath("$.candidates[0].requiredTechCoverage").value(0.5))
                    .andExpect(jsonPath("$.candidates[0].preferredTechCoverage").value(0.0));
            verify(metadata,times(1)).findCandidateDetails(anyCollection());
        });
    }
    @Test void realNotComparableGetIs200AndUnchanged() {
        unchanged(()->mvc.perform(get(ComparisonCandidatesControllerTest.ENDPOINT,6,61)).andExpect(status().isOk())
                .andExpect(jsonPath("$.selectionStatus").value("NOT_COMPARABLE"))
                .andExpect(jsonPath("$.reason").value("REQUIRED_FEATURES_MISSING"))
                .andExpect(jsonPath("$.confidence").value(nullValue()))
                .andExpect(jsonPath("$.candidates").value(hasSize(0))));
    }
    @Test void ownershipAndMissingEntitiesAreCheckedAgainstActualPublicIdsWithoutWrites() {
        unchanged(()->{
            mvc.perform(get(ComparisonCandidatesControllerTest.ENDPOINT,1,31)).andExpect(status().isBadRequest());
            mvc.perform(get(ComparisonCandidatesControllerTest.ENDPOINT,999,11)).andExpect(status().isNotFound());
            mvc.perform(get(ComparisonCandidatesControllerTest.ENDPOINT,1,999)).andExpect(status().isNotFound());
            mvc.perform(get(ComparisonCandidatesControllerTest.ENDPOINT,1,13)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.reason").value("NOT_IT_RECRUIT_UNIT"));
            mvc.perform(get(ComparisonCandidatesControllerTest.ENDPOINT,5,51)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.reason").value("RECRUIT_UNIT_NOT_CURRENT"));
        });
    }
}
