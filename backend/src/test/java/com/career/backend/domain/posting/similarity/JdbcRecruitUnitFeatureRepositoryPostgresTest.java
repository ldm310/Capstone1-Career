package com.career.backend.domain.posting.similarity;

import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static com.career.backend.domain.posting.similarity.SimilarityTestSupport.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;
import static com.career.backend.domain.posting.similarity.PostingCandidateSelectionResponse.*;

/** Real PostgreSQL only. No H2 substitute and no application/production config discovery. */
@EnabledIfEnvironmentVariable(named="POSTING_SIMILARITY_TEST_URL",matches=".+")
class JdbcRecruitUnitFeatureRepositoryPostgresTest {
    private JdbcTemplate jdbc;
    private JdbcRecruitUnitFeatureRepository repository;
    private DataSourceTransactionManager transactions;

    @BeforeEach void connect() {
        String url=System.getenv("POSTING_SIMILARITY_TEST_URL");
        if (url==null || !url.matches("jdbc:postgresql://(127\\.0\\.0\\.1|localhost):[0-9]+/extcrawler_test_similarity_[a-z0-9]+"))
            throw new IllegalArgumentException("An isolated local similarity test database is required");
        var ds=new DriverManagerDataSource(url,System.getenv("POSTING_SIMILARITY_TEST_USER"),System.getenv("POSTING_SIMILARITY_TEST_PASSWORD"));
        ds.setDriverClassName("org.postgresql.Driver");
        jdbc=new JdbcTemplate(ds);
        repository=new JdbcRecruitUnitFeatureRepository(new NamedParameterJdbcTemplate(ds));
        transactions=new DataSourceTransactionManager(ds);
    }
    private void readOnly(Runnable assertions) {
        var transaction=new TransactionTemplate(transactions);transaction.setReadOnly(true);
        transaction.executeWithoutResult(status -> {
            assertEquals("on",jdbc.queryForObject("SHOW transaction_read_only",String.class));
            assertions.run();
        });
    }
    private RecruitUnitFeatures find(RecruitUnitFeatureRepository.Snapshot s,long unitId) {
        return s.units().stream().filter(u -> u.unitId()==unitId).findFirst().orElseThrow();
    }
    @Test void currentItUnitsOnlyAndCompanyExclusionAreAppliedInSql() {
        readOnly(() -> {
            var data=repository.load(1);
            var units=data.units().stream().map(RecruitUnitFeatures::unitId).toList();
            assertTrue(units.containsAll(List.of(11L,12L,31L,32L,33L,52L,61L)));
            assertFalse(units.contains(13L));assertFalse(units.contains(21L));
            assertFalse(units.contains(41L));assertFalse(units.contains(51L));
            assertFalse(data.currentRunCounts().containsKey(2L));
            assertEquals(1,data.currentRunCounts().get(5L));
        });
    }
    @Test void independentActiveIdFilteringDeduplicatesWithoutLosingUnitsOrCapabilities() {
        readOnly(() -> {
            var data=repository.load(1);var target=find(data,11);
            assertEquals(ids(1),target.features(Category.REQUIRED).capabilityIds());
            assertEquals(ids(10,20),target.features(Category.REQUIRED).techIds());
            assertEquals(ids(2),target.features(Category.PREFERRED).capabilityIds());
            assertEquals(ids(20),target.features(Category.PREFERRED).techIds());
            assertEquals(ids(10),target.features(Category.DUTIES).techIds());
            assertEquals(IdSets.empty(),find(data,61).features(Category.REQUIRED));
            assertEquals(ids(2),find(data,62).features(Category.REQUIRED).capabilityIds());
            assertTrue(find(data,62).features(Category.REQUIRED).techIds().isEmpty());
            assertEquals(ids(2),find(data,12).features(Category.REQUIRED).capabilityIds());
        });
    }
    @Test void missingPostingNoExtractionAndNonItTargetAreDistinguished() {
        readOnly(() -> {
            assertNull(repository.load(999).targetCompanyId());
            assertEquals(Reason.NO_CURRENT_EXTRACTION,service(repository.load(8)).select(8).reason());
            assertEquals(Reason.NO_IT_RECRUIT_UNIT,service(repository.load(7)).select(7).reason());
        });
    }
    private Map<String,Object> snapshot() {
        Map<String,Object> result=new TreeMap<>();
        for (String table : jdbc.queryForList("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",String.class)) {
            String identifier='"'+table.replace("\"","\"\"")+'"';
            result.put(table,jdbc.queryForMap("SELECT count(*) AS rows,md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) AS hash FROM public."+identifier+" t"));
        }
        return result;
    }
    @Test void fullSelectionIsReadOnlyAndPublicDataDoesNotChange() {
        readOnly(() -> {
            var before=snapshot();
            var service=new PostingCandidateSelectionService(repository,resolver(),new KeywordPostingSimilarityScorer(),properties());
            var result=service.select(1);
            assertEquals(Status.SELECTED,result.status());assertEquals(2,result.units().size());
            assertEquals(31,result.units().getFirst().candidates().getFirst().unitId());
            assertEquals(33,result.units().get(1).candidates().getFirst().unitId());
            assertEquals(before,snapshot());
            assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM pg_namespace WHERE nspname='job'",Integer.class));
        });
    }
    @Test void existingUniqueIndexRejectsDuplicateCurrentRuns() {
        var tx=new TransactionTemplate(transactions);
        tx.executeWithoutResult(status -> {
            status.setRollbackOnly();
            assertThrows(org.springframework.dao.DataIntegrityViolationException.class,() -> addCurrentRun(102,1));
        });
    }
    @Test void corruptedTargetRunCountReturnsDataErrorInsteadOfPickingOne() { corruptAndVerify(1,102); }
    @Test void corruptedCandidateRunCountIsDetectedEvenWithoutItUnits() { corruptAndVerify(4,402); }
    private void corruptAndVerify(long postingId,long runId) {
        // Deliberately simulate a legacy/corrupt DB ONLY inside a rolled-back isolated test transaction.
        // The normal public unique index is never changed outside this test DB or after rollback.
        var tx=new TransactionTemplate(transactions);
        tx.executeWithoutResult(status -> {
            status.setRollbackOnly();
            jdbc.execute("DROP INDEX public.extraction_run_one_current");
            addCurrentRun(runId,postingId);
            var data=repository.load(1);
            assertEquals(2,data.currentRunCounts().get(postingId));
            var result=service(data).select(1);
            assertEquals(Status.DATA_ERROR,result.status());assertTrue(result.units().isEmpty());
            assertEquals(postingId,result.dataIssues().getFirst().postingId());
        });
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND indexname='extraction_run_one_current'",Integer.class));
    }
    private void addCurrentRun(long runId,long postingId) {
        jdbc.update("""
                INSERT INTO public.extraction_run(id,posting_id,model,prompt_version,dict_version,input_hash,
                    input_tokens,output_tokens,cost_usd,is_current) OVERRIDING SYSTEM VALUE
                VALUES(?,?,'fixture','fixture','fixture',repeat('0',64),0,0,0,true)
                """,runId,postingId);
    }
}
