package com.career.backend.domain.posting.similarity;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static com.career.backend.domain.posting.similarity.SimilarityTestSupport.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;
import static com.career.backend.domain.posting.similarity.PostingCandidateSelectionResponse.*;

class PostingCandidateEligibilityTest {
    private final IdSets empty=IdSets.empty();
    private RecruitUnitFeatures u(long posting,IdSets required,IdSets preferred,IdSets duties) {
        return unit(posting,posting,posting*100,"frontend",null,null,required,preferred,duties);
    }
    private UnitSelection select(RecruitUnitFeatures target,RecruitUnitFeatures candidate) {
        return service(snapshot(target,candidate)).select(target.postingId()).units().getFirst();
    }
    @Test void capabilityTwentyPercentIsRejectedEvenWithTechAndSupportingMatches() {
        var t=u(1,sets(ids(1,2,3,4,5),ids(10)),sets(ids(6),ids(11)),empty);
        var c=u(2,sets(ids(1),ids(10)),sets(ids(6),ids(11)),empty);
        var result=select(t,c);assertTrue(result.candidates().isEmpty());
        assertTrue(result.exclusions().getFirst().exclusionReasons().contains(Reason.REQUIRED_CAPABILITY_COVERAGE_TOO_LOW));
    }
    @Test void zeroRequiredTechIsRejectedRegardlessOfCapabilityAndSupportingMatches() {
        var t=u(1,sets(ids(1,2),ids(10)),sets(ids(6),ids(11)),empty);
        var c=u(2,sets(ids(1,2),ids(99)),sets(ids(6),ids(11)),empty);
        var result=select(t,c);assertTrue(result.candidates().isEmpty());
        assertTrue(result.exclusions().getFirst().exclusionReasons().contains(Reason.REQUIRED_TECH_INTERSECTION_TOO_LOW));
    }
    @Test void nonSparseRequiredEvidenceMustBeAtLeastTwo() {
        var result=select(u(1,sets(ids(1,2),Set.of()),sets(ids(3),Set.of()),empty),
                u(2,sets(ids(1),Set.of()),sets(ids(3),Set.of()),empty));
        assertTrue(result.candidates().isEmpty());
        assertTrue(result.exclusions().getFirst().exclusionReasons().contains(Reason.TOTAL_EVIDENCE_TOO_LOW));
    }
    @Test void singlePerfectRequiredFeatureAloneIsRejected() {
        var required=sets(ids(1),Set.of());
        var result=select(u(1,required,empty,empty),u(2,required,empty,empty));
        assertTrue(result.candidates().isEmpty());
        assertTrue(result.exclusions().getFirst().exclusionReasons().contains(Reason.SPARSE_SUPPORTING_EVIDENCE_TOO_LOW));
    }
    @Test void sparseRequiredWithDistinctPreferredEvidenceIsAllowedAndMarkedLowEvidence() {
        var required=sets(ids(1),Set.of());var supporting=sets(ids(2),Set.of());
        var candidate=select(u(1,required,supporting,empty),u(2,required,supporting,empty)).candidates().getFirst();
        assertEquals(Confidence.LOW,candidate.confidence());assertEquals(FeatureMode.REQUIRED,candidate.featureMode());
        assertEquals(2,candidate.evidenceCount());assertEquals(1,candidate.requiredEvidenceCount());
        assertEquals(1,candidate.supportingEvidenceCount());assertEquals(List.of(EvidenceFlag.LOW_EVIDENCE),candidate.evidenceFlags());
    }
    @Test void sparseRequiredWithDistinctDutyEvidenceIsAllowed() {
        var required=sets(Set.of(),ids(10));var supporting=sets(Set.of(),ids(20));
        assertEquals(2,select(u(1,required,empty,supporting),u(2,required,empty,supporting)).candidates().getFirst().evidenceCount());
    }
    @Test void repeatedRequiredIdInPreferredIsNotAdditionalEvidence() {
        var required=sets(ids(1),Set.of());
        assertTrue(select(u(1,required,required,required),u(2,required,required,required)).candidates().isEmpty());
    }
    @Test void sameSupportingIdInPreferredAndDutiesCountsOnce() {
        var required=sets(ids(1),Set.of());var support=sets(ids(2),Set.of());
        var result=select(u(1,required,support,support),u(2,required,support,support)).candidates().getFirst();
        assertEquals(2,result.evidenceCount());assertEquals(1,result.supportingEvidenceCount());
    }
    @Test void idSpacesAreIndependentEvidence() {
        var required=sets(ids(1),Set.of());var support=sets(Set.of(),ids(1));
        assertEquals(2,select(u(1,required,support,empty),u(2,required,support,empty)).candidates().getFirst().evidenceCount());
    }
    @Test void noRequiredFeaturesUsesTwoSupportingIntersectionsAndLowConfidence() {
        var preferred=sets(ids(1),Set.of());var duties=sets(Set.of(),ids(10));
        var selection=select(u(1,empty,preferred,duties),u(2,empty,preferred,duties));
        var result=selection.candidates().getFirst();
        assertEquals(FeatureMode.FALLBACK_FEATURES,selection.featureMode());
        assertEquals(FeatureMode.FALLBACK_FEATURES,result.featureMode());assertEquals(Confidence.LOW,result.confidence());
        assertEquals(List.of(EvidenceFlag.LOW_CONFIDENCE),result.evidenceFlags());assertEquals(2,result.evidenceCount());
    }
    @Test void fallbackTargetNeedsTwoDistinctFeaturesNotTwoMentions() {
        var one=sets(ids(1),Set.of());
        var result=select(u(1,empty,one,one),u(2,empty,one,one));
        assertEquals(Status.NOT_COMPARABLE,result.status());assertEquals(Reason.REQUIRED_FEATURES_MISSING,result.reason());
    }
    @Test void fallbackNeedsTwoIntersectionsNotJustTwoTargetFeatures() {
        var result=select(u(1,empty,sets(ids(1,2),Set.of()),empty),u(2,empty,sets(ids(1),Set.of()),empty));
        assertEquals(Status.NOT_COMPARABLE,result.status());assertEquals(Reason.REQUIRED_FEATURES_MISSING,result.reason());
        assertTrue(result.exclusions().getFirst().exclusionReasons().contains(Reason.FALLBACK_INTERSECTION_TOO_LOW));
    }
    @Test void fallbackStillDoesNotUseOtherRolesOrFamily() {
        var features=sets(ids(1,2),ids(10));
        var target=unit(1,1,100,"QA",null,null,empty,features,features);
        var candidate=unit(2,2,200,"Backend",null,null,empty,features,features);
        var result=select(target,candidate);assertTrue(result.candidates().isEmpty());assertFalse(result.familyExpansionAttempted());
    }
    @Test void requiredModeDefaultsAndAppliedThresholdsAreReturned() {
        var features=sets(ids(1),ids(10));
        var result=service(snapshot(u(1,features,empty,empty),u(2,features,empty,empty))).select(1);
        assertEquals(Confidence.HIGH,result.units().getFirst().candidates().getFirst().confidence());
        assertEquals(0.5,result.policy().thresholds().requiredCapabilityMinCoverage());
        assertEquals(2,result.policy().thresholds().minimumTotalEvidence());assertFalse(result.policy().jobFamilyExpansionEnabled());
    }
    @Test void thresholdsAreConfigurableAndExpansionCannotBeEnabledWithoutAllowlist() {
        var p=properties();p.setRequiredCapabilityMinCoverage(0.75);p.setRequiredTechMinIntersection(2);
        var target=u(1,sets(ids(1,2),ids(10,20)),empty,empty);
        var candidate=u(2,sets(ids(1),ids(10)),empty,empty);
        var result=service(snapshot(target,candidate),p).select(1).units().getFirst();
        assertEquals(2,result.exclusions().getFirst().exclusionReasons().size());
        p.setJobFamilyExpansionEnabled(true);
        try(var factory=jakarta.validation.Validation.buildDefaultValidatorFactory()){
            assertTrue(factory.getValidator().validate(p).stream().anyMatch(v->v.getPropertyPath().toString().equals("jobFamilyExpansionEnabled")));
        }
    }
}
