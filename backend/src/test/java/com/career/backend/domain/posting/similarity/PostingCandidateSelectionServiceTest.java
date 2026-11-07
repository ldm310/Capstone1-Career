package com.career.backend.domain.posting.similarity;

import com.career.backend.domain.common.NotFoundException;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static com.career.backend.domain.posting.similarity.SimilarityTestSupport.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;
import static com.career.backend.domain.posting.similarity.PostingCandidateSelectionResponse.*;

class PostingCandidateSelectionServiceTest {
    private final IdSets features=sets(ids(1,2),ids(10,20));
    private final RecruitUnitFeatures target=unit(1,1,100,"backend",features);
    private UnitSelection first(PostingCandidateSelectionResponse r) { return r.units().getFirst(); }

    @Test void excludesSameCompanyAndDoesNotClaimExactPostingEvidence() {
        var result=service(snapshot(target,unit(2,1,200,"backend",features),unit(3,2,300,"backend",features))).select(1);
        assertEquals(List.of(3L),first(result).candidates().stream().map(Candidate::postingId).toList());
        assertEquals("NOT_AVAILABLE",result.exactPostingEvidenceStatus());
        assertEquals(Stage.EXACT_ROLE,first(result).stage());
    }
    @Test void oneExactResultDoesNotFillRemainingSlotsFromFamily() {
        var exact=unit(2,2,200,"backend",sets(ids(1),ids(10)));
        var family=unit(3,3,300,"frontend",features);
        var selected=first(service(snapshot(target,exact,family)).select(1));
        assertEquals(1,selected.candidates().size());assertEquals(2,selected.candidates().getFirst().postingId());
        assertFalse(selected.familyExpansionAttempted());
    }
    @Test void noExpansionAfterAllExactCandidatesAreRejected() {
        var exact=unit(2,2,200,"backend",sets(ids(99),ids(99)));
        var family=unit(3,3,300,"frontend",features);
        var otherDomain=unit(4,4,400,"data_engineer",features);
        var selected=first(service(snapshot(target,exact,family,otherDomain)).select(1));
        assertFalse(selected.familyExpansionAttempted());assertEquals(Stage.NONE,selected.stage());
        assertTrue(selected.candidates().isEmpty());
        assertEquals(Reason.NO_REQUIRED_OVERLAP,selected.exclusions().getFirst().reason());
    }
    @Test void configurationCanDisableFamilyExpansion() {
        var p=properties();p.setJobFamilyExpansionEnabled(false);
        var selected=first(service(snapshot(target,unit(2,2,200,"frontend",features)),p).select(1));
        assertEquals(Status.NO_CANDIDATES,selected.status());assertFalse(selected.familyExpansionAttempted());
    }
    @Test void limitsThreeCompaniesTwoPostingsEachAndFiveTotal() {
        List<RecruitUnitFeatures> candidates=new ArrayList<>();
        for (int company=2;company<=6;company++) for (int p=0;p<4;p++) {
            long posting=company*10L+p;candidates.add(unit(posting,company,posting*10,"backend",features));
        }
        var selected=first(service(snapshot(target,candidates.toArray(RecruitUnitFeatures[]::new))).select(1)).candidates();
        assertEquals(5,selected.size());
        assertEquals(3,selected.stream().map(Candidate::companyId).distinct().count());
        for (long company : selected.stream().map(Candidate::companyId).distinct().toList())
            assertTrue(selected.stream().filter(c -> c.companyId()==company).count()<=2);
        assertEquals(List.of(20L,21L,30L,31L,40L),selected.stream().map(Candidate::postingId).toList());
    }
    @Test void limitsAreActuallyConfigurable() {
        var p=properties();p.setMaxCompanies(1);p.setMaxPostingsPerCompany(1);p.setMaxPostings(1);
        var selected=first(service(snapshot(target,unit(2,2,200,"backend",features),unit(3,3,300,"backend",features)),p).select(1));
        assertEquals(1,selected.candidates().size());
    }
    @Test void choosesBestCandidateUnitIndependentlyForEachTargetUnit() {
        var second=unit(1,1,101,"backend",sets(ids(2),ids(20)));
        var a=unit(2,2,200,"backend",sets(ids(1,2),ids(10)));
        var b=unit(2,2,201,"backend",sets(ids(2),ids(20)));
        var result=service(snapshot(target,second,a,b)).select(1);
        assertEquals(2,result.units().size());
        assertEquals(200,result.units().get(0).candidates().getFirst().unitId());
        assertEquals(201,result.units().get(1).candidates().getFirst().unitId());
        assertEquals(1,result.units().get(0).candidates().size());
    }
    @Test void noRequiredTargetFeaturesIsNotComparableEvenWithPreferredFeatures() {
        var t=unit(1,1,100,"backend",null,null,IdSets.empty(),features,features);
        var result=service(snapshot(t,unit(2,2,200,"backend",features))).select(1);
        assertEquals(Status.NOT_COMPARABLE,result.status());assertEquals(Reason.REQUIRED_FEATURES_MISSING,first(result).reason());
    }
    @Test void zeroRequiredIntersectionCannotBeRescuedByPreferredOrDuties() {
        var t=unit(1,1,100,"backend",null,null,features,features,features);
        var c=unit(2,2,200,"backend",null,null,sets(ids(99),ids(99)),features,features);
        var result=first(service(snapshot(t,c)).select(1));
        assertTrue(result.candidates().isEmpty());assertEquals(Reason.NO_REQUIRED_OVERLAP,result.exclusions().getFirst().reason());
    }
    @Test void missingCandidateRequiredFeaturesIsReported() {
        var result=first(service(snapshot(target,unit(2,2,200,"backend",IdSets.empty()))).select(1));
        assertTrue(result.exclusions().getFirst().exclusionReasons().contains(Reason.REQUIRED_TECH_INTERSECTION_TOO_LOW));
    }
    @Test void onlyTechRequiredTargetCanBeCompared() {
        var t=unit(1,1,100,"backend",sets(Set.of(),ids(10,20)));
        assertEquals(Status.SELECTED,service(snapshot(t,unit(2,2,200,"backend",features))).select(1).status());
    }
    @Test void unknownAndAmbiguousRolesAreNotGuessed() {
        var t=unit(1,1,100,"백엔드 프론트엔드",features);
        assertEquals(Reason.AMBIGUOUS_ROLE,first(service(snapshot(t)).select(1)).reason());
        var unknown=unit(1,1,100,"알수없음",features);
        assertEquals(Reason.UNKNOWN_ROLE,first(service(snapshot(unknown)).select(1)).reason());
        var result=first(service(snapshot(target,unit(2,2,200,"알수없음",features))).select(1));
        assertEquals(Reason.UNKNOWN_ROLE,result.exclusions().getFirst().reason());
    }
    @Test void duplicateCurrentRunOnTargetFailsClosed() {
        var data=new RecruitUnitFeatureRepository.Snapshot(1,1L,Map.of(1L,2),List.of(target));
        var result=service(data).select(1);
        assertEquals(Status.DATA_ERROR,result.status());assertTrue(result.units().isEmpty());
        assertEquals(2,result.dataIssues().getFirst().currentRunCount());
    }
    @Test void duplicateCandidateRunFailsClosedEvenWithNoCandidateUnits() {
        var data=new RecruitUnitFeatureRepository.Snapshot(1,1L,Map.of(1L,1,2L,2),List.of(target));
        var result=service(data).select(1);
        assertEquals(Status.DATA_ERROR,result.status());assertEquals(2,result.dataIssues().getFirst().postingId());
    }
    @Test void noCurrentRunAndNoItUnitsHaveDistinctReasons() {
        assertEquals(Reason.NO_CURRENT_EXTRACTION,service(new RecruitUnitFeatureRepository.Snapshot(1,1L,Map.of(1L,0),List.of())).select(1).reason());
        assertEquals(Reason.NO_IT_RECRUIT_UNIT,service(new RecruitUnitFeatureRepository.Snapshot(1,1L,Map.of(1L,1),List.of())).select(1).reason());
    }
    @Test void missingPostingAndInvalidIdAreRejected() {
        assertThrows(NotFoundException.class,() -> service(new RecruitUnitFeatureRepository.Snapshot(1,null,Map.of(),List.of())).select(1));
        assertThrows(IllegalArgumentException.class,() -> service(snapshot(target)).select(0));
    }
    @Test void inputOrderDoesNotChangeRanksOrRepresentative() {
        var a=unit(2,2,202,"backend",features);var b=unit(2,2,201,"backend",features);
        assertEquals(first(service(snapshot(target,a,b)).select(1)),first(service(snapshot(target,b,a)).select(1)));
        assertEquals(201,first(service(snapshot(target,a,b)).select(1)).candidates().getFirst().unitId());
    }
    @Test void oneUncomparableTargetDoesNotBlockAnotherTarget() {
        var second=unit(1,1,101,"backend",IdSets.empty());
        var result=service(snapshot(target,second,unit(2,2,200,"backend",features))).select(1);
        assertEquals(Status.SELECTED,result.status());
        assertEquals(Status.SELECTED,result.units().get(0).status());
        assertEquals(Reason.REQUIRED_FEATURES_MISSING,result.units().get(1).reason());
    }
    @Test void requiredTechBreaksCapabilityTieEvenWhenTargetCapabilityAxisIsEmpty() {
        var t=unit(1,1,100,"backend",null,null,sets(Set.of(),ids(10,20,30)),features,features);
        var preferred=unit(2,2,200,"backend",null,null,sets(Set.of(),ids(10,20)),features,features);
        var required=unit(3,3,300,"backend",sets(Set.of(),ids(10,20,30)));
        var result=first(service(snapshot(t,preferred,required)).select(1));
        assertEquals(List.of(3L,2L),result.candidates().stream().map(Candidate::postingId).toList());
    }
    @Test void invalidCandidateLimitsFailValidation() {
        try (var factory=jakarta.validation.Validation.buildDefaultValidatorFactory()) {
            var p=properties();assertTrue(factory.getValidator().validate(p).isEmpty());
            p.setMaxCompanies(0);p.setMaxPostingsPerCompany(0);p.setMaxPostings(0);
            assertEquals(3,factory.getValidator().validate(p).size());
        }
    }
}
