package com.career.backend.api.posting;

import com.career.backend.api.common.GlobalExceptionHandler;
import com.career.backend.domain.posting.similarity.*;
import com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;
import com.career.backend.domain.posting.similarity.RecruitUnitRoleResolver.RoleMatch;
import com.career.backend.domain.posting.similarity.RecruitUnitRoleResolver.Evidence;
import org.junit.jupiter.api.*;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import tools.jackson.databind.ObjectMapper;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static com.career.backend.domain.posting.similarity.PostingCandidateSelectionResponse.*;

class ComparisonCandidatesControllerTest {
    PostingCandidateSelectionService selection;
    ComparisonCandidateMetadataRepository metadata;
    MockMvc mvc;
    LocalValidatorFactoryBean validator;
    final RoleMatch role=new RoleMatch("backend","software",RecruitUnitRoleResolver.Status.RESOLVED,
            Evidence.RECRUIT_UNIT_NAME,List.of("backend"),"roles-mvp-2");
    final Policy policy=new Policy("keyword-mvp-2",3,2,5,false,new Thresholds(0.5,1,2,1,2,2));
    static final String ENDPOINT="/api/postings/{postingId}/recruit-units/{unitId}/comparison-candidates";

    @BeforeEach void setup() {
        selection=mock(PostingCandidateSelectionService.class);metadata=mock(ComparisonCandidateMetadataRepository.class);
        var taxonomy=new RoleTaxonomy();taxonomy.setVersion("roles-mvp-2");
        var query=new ComparisonCandidatesQueryService(selection,metadata,taxonomy);
        validator=new LocalValidatorFactoryBean();validator.afterPropertiesSet();
        mvc=MockMvcBuilders.standaloneSetup(new ComparisonCandidatesController(query))
                .setControllerAdvice(new GlobalExceptionHandler()).setValidator(validator).build();
        when(metadata.postingExists(1)).thenReturn(true);
        when(metadata.findUnit(11)).thenReturn(Optional.of(new ComparisonCandidateMetadataRepository.TargetUnit(11,1,true,true)));
    }
    @AfterEach void closeValidator() { validator.close(); }

    Candidate candidate(long posting,long company,long unit,boolean fallback) {
        var empty=IdSets.empty();var targetIds=new IdSets(Set.of(1L),Set.of(10L,20L));
        var sourceIds=new IdSets(Set.of(1L),Set.of(10L));
        var target=new RecruitUnitFeatures(1,1,10,11,"backend",null,null,
                fallback?Map.of(Category.PREFERRED,targetIds):Map.of(Category.REQUIRED,targetIds));
        var source=new RecruitUnitFeatures(posting,company,posting*10,unit,"backend",null,null,
                fallback?Map.of(Category.PREFERRED,sourceIds):Map.of(Category.REQUIRED,sourceIds));
        return new Candidate(1,posting,company,unit,posting*10,Stage.EXACT_ROLE,role,
                new KeywordPostingSimilarityScorer().score(target,source),fallback?Confidence.LOW:Confidence.HIGH,
                fallback?FeatureMode.FALLBACK_FEATURES:FeatureMode.REQUIRED,2,fallback?0:2,fallback?2:0,
                fallback?List.of(EvidenceFlag.LOW_CONFIDENCE):List.of(),List.of());
    }
    UnitSelection unit(long id,Status status,Reason reason,List<Candidate> candidates) {
        return new UnitSelection(id,10,role,status,reason,candidates.isEmpty()?Stage.NONE:Stage.EXACT_ROLE,
                false,candidates,List.of(),candidates.isEmpty()?FeatureMode.REQUIRED:candidates.getFirst().featureMode(),
                reason==Reason.NONE?List.of():List.of(reason));
    }
    void result(Status status,List<UnitSelection> units) {
        when(selection.select(1)).thenReturn(new PostingCandidateSelectionResponse(1,1L,status,Reason.NONE,"NOT_AVAILABLE",policy,List.of(),units));
    }
    void details(Candidate... candidates) {
        Map<Long,ComparisonCandidateMetadataRepository.CandidateDetails> rows=new HashMap<>();
        for(var c:candidates)rows.put(c.unitId(),new ComparisonCandidateMetadataRepository.CandidateDetails(
                c.postingId(),c.companyId(),"기업 "+c.companyId(),"공고 "+c.postingId(),c.unitId(),"모집 단위 "+c.unitId()));
        when(metadata.findCandidateDetails(anyCollection())).thenReturn(rows);
    }

    @Test void selectedReturnsOnlyRequestedUnitAndBatchEnrichesAllCandidatesOnce() throws Exception {
        var a=candidate(3,2,31,false);var b=candidate(5,3,51,false);
        result(Status.SELECTED,List.of(unit(11,Status.SELECTED,Reason.NONE,List.of(a,b)),
                unit(12,Status.SELECTED,Reason.NONE,List.of(candidate(99,99,999,false)))));
        details(a,b);
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isOk())
                .andExpect(jsonPath("$.postingId").value(1)).andExpect(jsonPath("$.recruitUnitId").value(11))
                .andExpect(jsonPath("$.selectionStatus").value("SELECTED"))
                .andExpect(jsonPath("$.confidence").value("HIGH")).andExpect(jsonPath("$.featureMode").value("REQUIRED"))
                .andExpect(jsonPath("$.roleCode").value("backend")).andExpect(jsonPath("$.roleResolutionSource").value("RECRUIT_UNIT_NAME"))
                .andExpect(jsonPath("$.evidenceCount").value(2)).andExpect(jsonPath("$.policyVersion").value("keyword-mvp-2"))
                .andExpect(jsonPath("$.taxonomyVersion").value("roles-mvp-2"))
                .andExpect(jsonPath("$.appliedCriteria.requiredCapabilityMinCoverage").value(0.5))
                .andExpect(jsonPath("$.appliedCriteria.minimumTotalEvidence").value(2))
                .andExpect(jsonPath("$.candidates").value(hasSize(2)))
                .andExpect(jsonPath("$.candidates[0].companyName").value("기업 2"))
                .andExpect(jsonPath("$.candidates[0].postingTitle").value("공고 3"))
                .andExpect(jsonPath("$.candidates[0].recruitUnitName").value("모집 단위 31"))
                .andExpect(jsonPath("$.candidates[0].requiredCapabilityCoverage").value(1.0))
                .andExpect(jsonPath("$.candidates[0].requiredTechCoverage").value(0.5))
                .andExpect(jsonPath("$.candidates[0].intersections.required.capabilityIds").value(contains(1)))
                .andExpect(jsonPath("$.candidates[0].intersections.required.techIds").value(contains(10)))
                .andExpect(jsonPath("$.candidates[0].preferredCapabilityCoverage").value(nullValue()))
                .andExpect(jsonPath("$.units").doesNotExist()).andExpect(jsonPath("$.dataIssues").doesNotExist())
                .andExpect(jsonPath("$.candidates[0].score").doesNotExist());
        verify(metadata,times(1)).findCandidateDetails(List.of(31L,51L));
        verify(selection,times(1)).select(1);
    }
    @Test void lowFallbackPreservesNullRequiredCoverageAndExplicitEvidenceFlags() throws Exception {
        var c=candidate(3,2,31,true);details(c);result(Status.SELECTED,List.of(unit(11,Status.SELECTED,Reason.NONE,List.of(c))));
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isOk())
                .andExpect(jsonPath("$.confidence").value("LOW")).andExpect(jsonPath("$.featureMode").value("FALLBACK_FEATURES"))
                .andExpect(jsonPath("$.candidates[0].requiredCapabilityCoverage").value(nullValue()))
                .andExpect(jsonPath("$.candidates[0].requiredTechCoverage").value(nullValue()))
                .andExpect(jsonPath("$.candidates[0].requiredEvidenceCount").value(0))
                .andExpect(jsonPath("$.candidates[0].supportingEvidenceCount").value(2))
                .andExpect(jsonPath("$.candidates[0].evidenceFlags").value(org.hamcrest.Matchers.contains("LOW_CONFIDENCE")));
    }
    @Test void noCandidatesIs200EvenWhenAnotherUnitWasSelected() throws Exception {
        var missing=unit(11,Status.NO_CANDIDATES,Reason.NO_ELIGIBLE_CANDIDATE,List.of());
        var exclusion=new Exclusion(3,31,Reason.REQUIRED_TECH_INTERSECTION_TOO_LOW,role,List.of(Reason.REQUIRED_TECH_INTERSECTION_TOO_LOW));
        missing=new UnitSelection(11,10,role,missing.status(),missing.reason(),Stage.NONE,false,List.of(),List.of(exclusion),FeatureMode.REQUIRED,missing.exclusionReasons());
        result(Status.SELECTED,List.of(missing,unit(12,Status.SELECTED,Reason.NONE,List.of(candidate(3,2,31,false)))));
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isOk())
                .andExpect(jsonPath("$.selectionStatus").value("NO_CANDIDATES"))
                .andExpect(jsonPath("$.confidence").value(nullValue())).andExpect(jsonPath("$.evidenceCount").value(0))
                .andExpect(jsonPath("$.exclusionReasons").value(contains("NO_ELIGIBLE_CANDIDATE","REQUIRED_TECH_INTERSECTION_TOO_LOW")))
                .andExpect(jsonPath("$.candidates").value(hasSize(0)));
        verify(metadata,never()).findCandidateDetails(anyCollection());
    }
    @Test void notComparableIs200WithNoInventedConfidence() throws Exception {
        result(Status.NOT_COMPARABLE,List.of(unit(11,Status.NOT_COMPARABLE,Reason.REQUIRED_FEATURES_MISSING,List.of())));
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isOk())
                .andExpect(jsonPath("$.selectionStatus").value("NOT_COMPARABLE"))
                .andExpect(jsonPath("$.reason").value("REQUIRED_FEATURES_MISSING"))
                .andExpect(jsonPath("$.confidence").value(nullValue())).andExpect(jsonPath("$.candidates").value(hasSize(0)));
        verify(metadata,never()).findCandidateDetails(anyCollection());
    }
    @Test void foreignPostingUnitIs400BeforeSelectionRuns() throws Exception {
        when(metadata.findUnit(11)).thenReturn(Optional.of(new ComparisonCandidateMetadataRepository.TargetUnit(11,3,true,true)));
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isBadRequest()).andExpect(jsonPath("$.status").value(400));
        verifyNoInteractions(selection);
    }
    @Test void missingPostingIs404BeforeUnitLookup() throws Exception {
        mvc.perform(get(ENDPOINT,999,11)).andExpect(status().isNotFound());
        verify(metadata,never()).findUnit(anyLong());verifyNoInteractions(selection);
    }
    @Test void missingUnitIs404() throws Exception {
        when(metadata.findUnit(11)).thenReturn(Optional.empty());
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isNotFound());verifyNoInteractions(selection);
    }
    @Test void duplicateCurrentExtractionDataErrorIs409() throws Exception {
        when(selection.select(1)).thenReturn(new PostingCandidateSelectionResponse(1,1L,Status.DATA_ERROR,
                Reason.DUPLICATE_CURRENT_EXTRACTION,"NOT_AVAILABLE",policy,
                List.of(new DataIssue(3,2,Reason.DUPLICATE_CURRENT_EXTRACTION)),List.of()));
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.message").value(containsString("DUPLICATE_CURRENT_EXTRACTION")));
        verify(metadata,never()).findCandidateDetails(anyCollection());
    }
    @Test void historicalExistingUnitIs200NotComparableRatherThan404() throws Exception {
        when(metadata.findUnit(11)).thenReturn(Optional.of(new ComparisonCandidateMetadataRepository.TargetUnit(11,1,false,true)));
        result(Status.SELECTED,List.of(unit(12,Status.SELECTED,Reason.NONE,List.of(candidate(3,2,31,false)))));
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isOk())
                .andExpect(jsonPath("$.reason").value("RECRUIT_UNIT_NOT_CURRENT"))
                .andExpect(jsonPath("$.featureMode").value(nullValue())).andExpect(jsonPath("$.roleResolutionSource").value("UNKNOWN"));
    }
    @Test void nonItExistingUnitIs200NotComparable() throws Exception {
        when(metadata.findUnit(11)).thenReturn(Optional.of(new ComparisonCandidateMetadataRepository.TargetUnit(11,1,true,false)));
        result(Status.NOT_COMPARABLE,List.of());
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isOk())
                .andExpect(jsonPath("$.reason").value("NOT_IT_RECRUIT_UNIT"));
    }
    @Test void missingEnrichmentDataFails409InsteadOfSilentlyChangingCandidateRanks() throws Exception {
        result(Status.SELECTED,List.of(unit(11,Status.SELECTED,Reason.NONE,List.of(candidate(3,2,31,false)))));
        when(metadata.findCandidateDetails(anyCollection())).thenReturn(Map.of());
        mvc.perform(get(ENDPOINT,1,11)).andExpect(status().isConflict());
    }
    @Test void nonpositiveIdsAre400() throws Exception {
        mvc.perform(get(ENDPOINT,0,11)).andExpect(status().isBadRequest());
        mvc.perform(get(ENDPOINT,1,-1)).andExpect(status().isBadRequest());verifyNoInteractions(selection);
    }
    @Test void openApiExamplesAreValidAndKeepUncomputableCoverageNull() {
        var mapper=new ObjectMapper();
        for(String example:List.of(ComparisonCandidatesExamples.SELECTED,ComparisonCandidatesExamples.LOW,
                ComparisonCandidatesExamples.NO_CANDIDATES,ComparisonCandidatesExamples.NOT_COMPARABLE))
            assertTrue(mapper.readTree(example).has("appliedCriteria"));
        var low=mapper.readTree(ComparisonCandidatesExamples.LOW);
        assertEquals("LOW",low.get("confidence").asText());
        assertTrue(low.get("candidates").get(0).get("requiredTechCoverage").isNull());
    }
}
