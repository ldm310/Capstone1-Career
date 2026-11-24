package com.career.backend.api.posting;

import com.career.backend.api.common.GlobalExceptionHandler;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.support.TransactionTemplate;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@EnabledIfEnvironmentVariable(named="POSTING_SIMILARITY_TEST_URL",matches=".+")
class ExternalPassCollectionStatusPostgresTest {
    JdbcTemplate jdbc;
    DriverManagerDataSource ds;
    @BeforeEach void setup() {
        String url=System.getenv("POSTING_SIMILARITY_TEST_URL");
        if(!url.matches("jdbc:postgresql://(127\\.0\\.0\\.1|localhost):[0-9]+/extcrawler_test_similarity_[a-z0-9]+"))
            throw new IllegalArgumentException("Isolated local fixture database required");
        ds=new DriverManagerDataSource(url,System.getenv("POSTING_SIMILARITY_TEST_USER"),System.getenv("POSTING_SIMILARITY_TEST_PASSWORD"));
        jdbc=new JdbcTemplate(ds);
    }
    Map<String,Object> snapshot() {
        Map<String,Object> result=new TreeMap<>();
        for(var row:jdbc.queryForList("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('public','external_data') ORDER BY 1,2")) {
            String schema=row.get("schemaname").toString(),table=row.get("tablename").toString();
            result.put(schema+"."+table,jdbc.queryForMap("SELECT count(*) AS n,md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) AS h FROM \""+schema+"\".\""+table.replace("\"","\"\"")+"\" t"));
        }
        result.put("sequences",jdbc.queryForList("SELECT schemaname,sequencename,last_value FROM pg_sequences WHERE schemaname IN ('public','external_data') ORDER BY 1,2"));
        return result;
    }
    @Test void realRepositoryReadsReusedMaterialsWithoutAnyPublicOrExternalWrites() {
        var selection=mock(ComparisonCandidatesQueryService.class);
        var candidate=mock(ComparisonCandidatesResponse.Candidate.class);
        when(candidate.postingId()).thenReturn(3L);when(candidate.recruitUnitId()).thenReturn(31L);
        when(candidate.companyId()).thenReturn(2L);when(candidate.confidence()).thenReturn("HIGH");
        when(selection.get(1,11)).thenReturn(result(1,11,List.of(candidate)));
        var repository=new ExternalPassCollectionStatusRepository(new NamedParameterJdbcTemplate(ds));
        var service=new ExternalPassCollectionStatusService(selection,repository);
        var mvc=MockMvcBuilders.standaloneSetup(new ExternalPassCollectionStatusController(service))
                .setControllerAdvice(new GlobalExceptionHandler()).build();
        var before=snapshot();
        var tx=new TransactionTemplate(new DataSourceTransactionManager(ds));tx.setReadOnly(true);
        tx.executeWithoutResult(status->{
            assertEquals("on",jdbc.queryForObject("SHOW transaction_read_only",String.class));
            try {mvc.perform(get(ExternalPassCollectionStatusTest.PATH,1,11)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.collectionStatus").value("READY"))
                    .andExpect(jsonPath("$.materialCount").value(5))
                    .andExpect(jsonPath("$.requestedCompanyCount").value(1))
                    .andExpect(jsonPath("$.candidates[0].reused").value(true));
            }catch(Exception e){throw new AssertionError(e);}
        });
        assertEquals(before,snapshot());
    }
    @Test void directSameCompanyRoleMaterialsTakePrecedenceWithoutCreatingRequests() {
        var selection=mock(ComparisonCandidatesQueryService.class);
        when(selection.get(2,21)).thenReturn(result(2,21,List.of()));
        var service=new ExternalPassCollectionStatusService(selection,
                new ExternalPassCollectionStatusRepository(new NamedParameterJdbcTemplate(ds)));
        var before=snapshot();
        var tx=new TransactionTemplate(new DataSourceTransactionManager(ds));tx.setReadOnly(true);
        tx.executeWithoutResult(status->{var result=service.get(2,21);assertEquals("DIRECT",result.source());assertEquals(5,result.materialCount());});
        assertEquals(before,snapshot());
    }
    private ComparisonCandidatesResponse result(long posting,long unit,List<ComparisonCandidatesResponse.Candidate> candidates) {
        return new ComparisonCandidatesResponse(posting,unit,candidates.isEmpty()?"NO_CANDIDATES":"SELECTED","NONE",null,
                "REQUIRED","backend","RECRUIT_UNIT_NAME",0,List.of(),"keyword-mvp-2","roles-mvp-2",
                new ComparisonCandidatesResponse.AppliedCriteria(3,2,5,false,.5,1,2,1,2,2),candidates);
    }
}
