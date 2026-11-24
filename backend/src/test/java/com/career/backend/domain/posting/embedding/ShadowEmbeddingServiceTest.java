package com.career.backend.domain.posting.embedding;

import org.junit.jupiter.api.*;
import org.springframework.core.io.ClassPathResource;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.career.backend.domain.posting.embedding.ShadowEmbeddingRepository.*;
import com.career.backend.domain.posting.embedding.ShadowEmbeddingService.UnitRef;

class ShadowEmbeddingServiceTest {
    ShadowEmbeddingRepository repository;
    EmbeddingShadowProperties config;
    ShadowEmbeddingService service;
    String taxonomy;
    @BeforeEach void setup() throws Exception {
        repository=mock(ShadowEmbeddingRepository.class);config=new EmbeddingShadowProperties();config.setDimension(3);
        service=new ShadowEmbeddingService(repository,config);
        String source=new ClassPathResource("posting-similarity.properties").getContentAsString(StandardCharsets.UTF_8).replace("\r\n","\n");
        taxonomy=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(source.getBytes(StandardCharsets.UTF_8)));
    }
    Row row(long id,long unit,String category,double...vector) {
        return new Row(id,unit,unit*10,category,"same","same",taxonomy,"backend","ELIGIBLE","READY",vector);
    }
    EmbeddingShadowResult score(Row...rows) {
        when(repository.load(anySet(),same(config))).thenReturn(new Snapshot(true,List.of(rows)));
        return service.score(new UnitRef(11,110,"backend"),List.of(new UnitRef(31,310,"backend"))).get(31L);
    }
    @Test void categoriesAreIndependentAndEachTargetUsesBestCandidateThenMean() {
        var result=score(row(1,11,"REQUIRED",1,0,0),row(2,11,"REQUIRED",0,1,0),
                row(3,31,"REQUIRED",1,0,0),row(4,11,"PREFERRED",0,0,1),row(5,31,"PREFERRED",0,0,-1),
                row(6,11,"DUTIES",1,0,0),row(7,31,"DUTIES",0,1,0));
        assertEquals(.5,result.required());assertEquals(-1.,result.preferred());
        assertEquals(0.,result.duties());assertEquals(4,result.matchedCount());
        assertEquals("READY",result.status());
    }
    @Test void noComparablePairsRemainNullAndZeroCount() {
        var result=score(row(1,11,"REQUIRED",1,0,0),row(2,31,"PREFERRED",1,0,0));
        assertNull(result.required());assertNull(result.preferred());
        assertNull(result.duties());assertEquals(0,result.matchedCount());
    }
    @Test void missingAndMalformedVectorsDoNotBecomeZeroScores() {
        var result=score(row(1,11,"REQUIRED",1,0,0),row(2,31,"REQUIRED",Double.NaN,0,1));
        assertNull(result.required());assertEquals("UNAVAILABLE",result.status());
        assertFalse(CosineSimilarity.valid(new double[]{0,0,0},3));assertFalse(CosineSimilarity.valid(new double[]{1,2},3));
        assertNull(ShadowEmbeddingRepository.parse(null));assertArrayEquals(new double[]{1,0,0},ShadowEmbeddingRepository.parse("{1,0,0}"));
    }
    @Test void partialAndStaleSourcesAreExplicitAndNeverScoreStaleVectors() {
        var old=new Row(4,31,310,"REQUIRED","new","old",taxonomy,"backend","ELIGIBLE","READY",new double[]{0,1,0});
        var result=score(row(1,11,"REQUIRED",1,0,0),row(2,31,"REQUIRED",1,0,0),old);
        assertEquals("PARTIAL",result.status());assertEquals(1.,result.required());
        result=score(row(1,11,"REQUIRED",1,0,0),old);
        assertEquals("STALE",result.status());assertNull(result.required());
    }
    @Test void unavailableDatabaseAndAbsentSchemaFailOpenWithoutScores() {
        when(repository.load(anySet(),same(config))).thenThrow(new IllegalStateException("private database details"));
        var result=service.score(new UnitRef(11,110,"backend"),List.of(new UnitRef(31,310,"backend"))).get(31L);
        assertEquals("UNAVAILABLE",result.status());assertNull(result.required());
        when(repository.load(anySet(),same(config))).thenReturn(new Snapshot(false,List.of()));
        assertEquals("NOT_GENERATED",service.score(new UnitRef(11,110,"backend"),List.of(new UnitRef(31,310,"backend"))).get(31L).status());
    }
    @Test void offDoesNotReadDatabase() {
        config.setMode(EmbeddingShadowProperties.Mode.OFF);
        assertEquals("DISABLED",service.score(new UnitRef(11,110,"backend"),List.of(new UnitRef(31,310,"backend"))).get(31L).status());
        verifyNoInteractions(repository);
    }
    @Test void identicalSemanticVectorsCannotMakeJavaAndJavaScriptAnExactTechMatch() {
        var idsJava=new com.career.backend.domain.posting.similarity.RecruitUnitFeatures.IdSets(Set.of(1L),Set.of(10L));
        var idsJavaScript=new com.career.backend.domain.posting.similarity.RecruitUnitFeatures.IdSets(Set.of(1L),Set.of(20L));
        var target=new com.career.backend.domain.posting.similarity.RecruitUnitFeatures(1,1,101,11,"backend",null,null,
                Map.of(com.career.backend.domain.posting.similarity.RecruitUnitFeatures.Category.REQUIRED,idsJava));
        var candidate=new com.career.backend.domain.posting.similarity.RecruitUnitFeatures(3,2,301,31,"backend",null,null,
                Map.of(com.career.backend.domain.posting.similarity.RecruitUnitFeatures.Category.REQUIRED,idsJavaScript));
        assertEquals(1.,score(row(1,11,"REQUIRED",1,0,0),row(2,31,"REQUIRED",1,0,0)).required());
        var keyword=new com.career.backend.domain.posting.similarity.KeywordPostingSimilarityScorer().score(target,candidate);
        assertEquals(0,keyword.category(com.career.backend.domain.posting.similarity.RecruitUnitFeatures.Category.REQUIRED).tech().intersectionCount());
        assertEquals(0.,keyword.category(com.career.backend.domain.posting.similarity.RecruitUnitFeatures.Category.REQUIRED).tech().coverage());
    }
}
