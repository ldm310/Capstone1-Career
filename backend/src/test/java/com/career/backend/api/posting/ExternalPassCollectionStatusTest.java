package com.career.backend.api.posting;

import com.career.backend.api.common.GlobalExceptionHandler;
import com.career.backend.domain.common.NotFoundException;
import org.junit.jupiter.api.*;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.time.OffsetDateTime;
import java.util.*;
import static com.career.backend.api.posting.ExternalPassCollectionStatusRepository.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ExternalPassCollectionStatusTest {
    static final String PATH="/api/postings/{p}/recruit-units/{u}/external-pass-collection-status";
    ComparisonCandidatesQueryService selection;
    ExternalPassCollectionStatusRepository repository;
    ExternalPassCollectionStatusService service;
    MockMvc mvc;
    final OffsetDateTime at=OffsetDateTime.parse("2026-11-08T00:00:00+09:00");
    @BeforeEach void setup() {
        selection=mock(ComparisonCandidatesQueryService.class);repository=mock(ExternalPassCollectionStatusRepository.class);
        service=new ExternalPassCollectionStatusService(selection,repository);
        mvc=MockMvcBuilders.standaloneSetup(new ExternalPassCollectionStatusController(service))
                .setControllerAdvice(new GlobalExceptionHandler()).build();
        when(repository.request(1,11,"keyword-mvp-2")).thenReturn(Optional.empty());
        selected("SELECTED",candidate(3,31,2,"HIGH"));
    }
    ComparisonCandidatesResponse.Candidate candidate(long posting,long unit,long company,String confidence) {
        var c=mock(ComparisonCandidatesResponse.Candidate.class);
        when(c.postingId()).thenReturn(posting);when(c.recruitUnitId()).thenReturn(unit);
        when(c.companyId()).thenReturn(company);when(c.confidence()).thenReturn(confidence);return c;
    }
    void selected(String status,ComparisonCandidatesResponse.Candidate... candidates) {
        when(selection.get(1,11)).thenReturn(new ComparisonCandidatesResponse(1,11,status,"NONE",null,"REQUIRED",
                "backend","RECRUIT_UNIT_NAME",0,List.of(),"keyword-mvp-2","roles-mvp-2",
                new ComparisonCandidatesResponse.AppliedCriteria(3,2,5,false,.5,1,2,1,2,2),List.of(candidates)));
    }
    Row row(long posting,long unit,long company,String confidence,String status,Set<Long> ids) {
        return new Row(unit,posting,company,"backend",confidence,true,"READY".equals(status),status,
                "FAILED".equals(status)?"sensitive database detail":null,at,at,at,ids);
    }
    void registered(Row... rows) {
        when(repository.request(1,11,"keyword-mvp-2")).thenReturn(Optional.of(new Request(1,"backend",false)));
        when(repository.rows(1)).thenReturn(List.of(rows));
    }
    @Test void unrequestedIsExplicitAndDoesNotPretendAJobWasQueued() throws Exception {
        mvc.perform(get(PATH,1,11)).andExpect(status().isOk()).andExpect(jsonPath("$.collectionStatus").value("NOT_REQUESTED"))
                .andExpect(jsonPath("$.requestedCompanyCount").value(0)).andExpect(jsonPath("$.highCandidateCount").value(1))
                .andExpect(jsonPath("$.retryable").value(false));
        verify(repository,never()).rows(anyLong());
    }
    @Test void pendingIsVisibleWithoutRegisteringWork() throws Exception {
        registered(row(3,31,2,"HIGH","PENDING",Set.of()));
        mvc.perform(get(PATH,1,11)).andExpect(status().isOk()).andExpect(jsonPath("$.collectionStatus").value("PENDING"))
                .andExpect(jsonPath("$.requestedCompanyCount").value(1));
    }
    @Test void runningPrecedesPendingAndTerminalFailures() {
        selected("SELECTED",candidate(3,31,2,"HIGH"),candidate(5,52,3,"HIGH"));
        registered(row(3,31,2,"HIGH","FAILED",Set.of()),row(5,52,3,"HIGH","RUNNING",Set.of()));
        assertEquals("RUNNING",service.get(1,11).collectionStatus());
    }
    @Test void highMaterialsTakePriorityOverPreviouslyCollectedLowData() {
        selected("SELECTED",candidate(3,31,2,"HIGH"),candidate(5,52,3,"LOW"));
        registered(row(3,31,2,"HIGH","READY",Set.of(1L,2L,3L,4L,5L)),row(5,52,3,"LOW","READY",Set.of(6L)));
        var result=service.get(1,11);assertEquals("READY",result.collectionStatus());assertEquals(5,result.materialCount());
    }
    @Test void lowMaterialsAreReferenceFallbackWhenHighIsInsufficient() {
        selected("SELECTED",candidate(3,31,2,"HIGH"),candidate(5,52,3,"LOW"));
        registered(row(3,31,2,"HIGH","INSUFFICIENT",Set.of(1L)),row(5,52,3,"LOW","READY",Set.of(2L,3L,4L,5L)));
        var result=service.get(1,11);assertEquals("READY",result.collectionStatus());assertEquals(1,result.lowCandidateCount());
        assertEquals("LOW",result.candidates().get(1).confidence());
    }
    @Test void previouslyCollectedLowDataDoesNotBypassRunningHighWork() {
        selected("SELECTED",candidate(3,31,2,"HIGH"),candidate(5,52,3,"LOW"));
        registered(row(3,31,2,"HIGH","RUNNING",Set.of()),row(5,52,3,"LOW","READY",Set.of(1L,2L,3L,4L,5L)));
        var result=service.get(1,11);assertEquals("RUNNING",result.collectionStatus());assertEquals(0,result.materialCount());
        assertNull(result.completedAt());
    }
    @Test void sharedCompanyAndMaterialCountsAreDeduplicated() {
        selected("SELECTED",candidate(3,31,2,"HIGH"),candidate(4,32,2,"HIGH"));
        registered(row(3,31,2,"HIGH","READY",Set.of(1L,2L,3L,4L,5L)),row(4,32,2,"HIGH","READY",Set.of(1L,2L,3L,4L,5L)));
        var result=service.get(1,11);assertEquals(5,result.materialCount());assertEquals(1,result.requestedCompanyCount());assertEquals(1,result.readyCompanyCount());
    }
    @Test void directMaterialsAreUsedBeforeCandidateRequests() {
        when(repository.directIds(1,"backend")).thenReturn(Set.of(1L,2L,3L,4L,5L));
        var result=service.get(1,11);assertEquals("DIRECT",result.source());assertEquals("READY",result.collectionStatus());
        assertEquals(0,result.selectedCandidateCount());verify(repository,never()).request(anyLong(),anyLong(),anyString());
    }
    @Test void insufficientDoesNotAutomaticallyRetry() {
        registered(row(3,31,2,"HIGH","INSUFFICIENT",Set.of(1L)));
        var result=service.get(1,11);assertEquals("INSUFFICIENT",result.collectionStatus());assertFalse(result.retryable());
    }
    @Test void twoDirectSamplesAreReadyButOneIsInsufficient() {
        when(repository.directIds(1,"backend")).thenReturn(Set.of(1L,2L));
        assertEquals("READY",service.get(1,11).collectionStatus());
        when(repository.directIds(1,"backend")).thenReturn(Set.of(1L));
        assertEquals("INSUFFICIENT",service.get(1,11).collectionStatus());
    }
    @Test void twoHighSamplesAreEnoughWithoutLowFallback() {
        selected("SELECTED",candidate(3,31,2,"HIGH"),candidate(5,52,3,"LOW"));
        registered(row(3,31,2,"HIGH","READY",Set.of(1L,2L)),row(5,52,3,"LOW","READY",Set.of(3L)));
        var result=service.get(1,11);
        assertEquals("READY",result.collectionStatus());assertEquals(2,result.materialCount());
    }
    @Test void failureOnlyExposesAnAllowlistedSafeCode() throws Exception {
        registered(row(3,31,2,"HIGH","FAILED",Set.of()));
        var response=mvc.perform(get(PATH,1,11)).andExpect(status().isOk())
                .andExpect(jsonPath("$.safeErrorCode").value("COLLECTION_FAILED"))
                .andExpect(jsonPath("$.retryable").value(false)).andReturn().getResponse().getContentAsString();
        assertFalse(response.contains("sensitive"));
    }
    @Test void emptySelectionExplainsWhyWithoutInventingARequest() {
        selected("NO_CANDIDATES");var result=service.get(1,11);
        assertEquals("INSUFFICIENT",result.collectionStatus());assertEquals("비교할 유사 공고를 찾지 못했습니다.",result.userMessage());
        selected("NOT_COMPARABLE");assertEquals("현재 공고의 비교 기준이 부족합니다.",service.get(1,11).userMessage());
    }
    @Test void ownershipMissingAndDataErrorsKeep400404409() throws Exception {
        when(selection.get(1,31)).thenThrow(new IllegalArgumentException("소속 불일치"));
        when(selection.get(999,11)).thenThrow(new NotFoundException("공고 없음"));
        when(selection.get(1,999)).thenThrow(new NotFoundException("모집 단위 없음"));
        when(selection.get(1,12)).thenThrow(new IllegalStateException("데이터 오류"));
        mvc.perform(get(PATH,1,31)).andExpect(status().isBadRequest());
        mvc.perform(get(PATH,999,11)).andExpect(status().isNotFound());
        mvc.perform(get(PATH,1,999)).andExpect(status().isNotFound());
        mvc.perform(get(PATH,1,12)).andExpect(status().isConflict());
    }
    @Test void staleProvenanceAndUninstalledSchemaAre409() throws Exception {
        registered(row(5,52,3,"HIGH","READY",Set.of()));
        mvc.perform(get(PATH,1,11)).andExpect(status().isConflict());
        doThrow(new IllegalStateException("스키마 적용 필요")).when(repository).ensureInstalled();
        mvc.perform(get(PATH,1,11)).andExpect(status().isConflict());
    }
}
