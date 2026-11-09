package com.career.backend.domain.posting.embedding;

import javax.sql.DataSource;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.TransactionTemplate;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import com.career.backend.domain.posting.embedding.ShadowEmbeddingService.UnitRef;

@EnabledIfEnvironmentVariable(named="POSTING_SIMILARITY_TEST_URL",matches=".+")
class ShadowEmbeddingPostgresTest {
    @Configuration @EnableTransactionManagement static class Transactions {}
    AnnotationConfigApplicationContext context;
    JdbcTemplate jdbc;
    ShadowEmbeddingService service;
    TransactionTemplate outer;
    @BeforeEach void setup() {
        String url=System.getenv("POSTING_SIMILARITY_TEST_URL");
        assertTrue(url.matches("jdbc:postgresql://(127\\.0\\.0\\.1|localhost):[0-9]+/extcrawler_test_similarity_[a-z0-9]+"));
        var ds=new DriverManagerDataSource(url,System.getenv("POSTING_SIMILARITY_TEST_USER"),System.getenv("POSTING_SIMILARITY_TEST_PASSWORD"));
        var tm=new DataSourceTransactionManager(ds);jdbc=new JdbcTemplate(ds);
        context=new AnnotationConfigApplicationContext();context.register(Transactions.class);
        context.registerBean(DataSource.class,()->ds);context.registerBean("transactionManager",DataSourceTransactionManager.class,()->tm);
        context.registerBean(ShadowEmbeddingRepository.class);context.refresh();
        var config=new EmbeddingShadowProperties();config.setDimension(3);
        service=new ShadowEmbeddingService(context.getBean(ShadowEmbeddingRepository.class),config);
        outer=new TransactionTemplate(tm);outer.setReadOnly(true);
    }
    @AfterEach void close(){context.close();}
    EmbeddingShadowResult score(){return service.score(new UnitRef(11,101,"backend"),List.of(new UnitRef(31,301,"backend"))).get(31L);}
    @Test void realArrayVectorsAreReadOnlyAndModelConfigMismatchPreservesNull() {
        var count=jdbc.queryForObject("SELECT count(*) FROM public.be_embedding_cache",Long.class);
        outer.executeWithoutResult(tx->{
            assertEquals("on",jdbc.queryForObject("SHOW transaction_read_only",String.class));
            var result=score();assertNotNull(result.required());
            assertTrue(result.matchedCount()>0);
            var config=new EmbeddingShadowProperties();config.setDimension(2);
            var other=new ShadowEmbeddingService(context.getBean(ShadowEmbeddingRepository.class),config);
            assertNull(other.score(new UnitRef(11,101,"backend"),List.of(new UnitRef(31,301,"backend"))).get(31L).required());
            assertEquals(1,jdbc.queryForObject("SELECT 1",Integer.class));
        });
        assertEquals(count,jdbc.queryForObject("SELECT count(*) FROM public.be_embedding_cache",Long.class));
    }
    @Test void realSqlFailureIsolatedInNewTransactionCannotAbortKeywordTransaction() {
        jdbc.execute("ALTER VIEW public.be_requirement_embedding_view RENAME COLUMN embedding_text TO hidden_embedding_text");
        try {
            outer.executeWithoutResult(tx->{
                assertEquals("UNAVAILABLE",score().status());
                assertEquals(1,jdbc.queryForObject("SELECT 1",Integer.class));
                assertEquals("on",jdbc.queryForObject("SHOW transaction_read_only",String.class));
                assertTrue(jdbc.queryForObject("SELECT count(*) FROM public.requirement",Long.class)>0);
            });
        }finally{jdbc.execute("ALTER VIEW public.be_requirement_embedding_view RENAME COLUMN hidden_embedding_text TO embedding_text");}
    }
}
