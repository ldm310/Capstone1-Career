package com.career.backend.domain.posting.similarity;

import org.springframework.stereotype.Component;
import java.util.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;
import static com.career.backend.domain.posting.similarity.PostingCandidateSelectionResponse.*;

/** Admission checks precede ranking. Evidence is distinct typed IDs, not repeated mentions/categories. */
@Component
public class PostingCandidateEligibility {
    private final PostingSimilarityProperties properties;
    public PostingCandidateEligibility(PostingSimilarityProperties properties) { this.properties=properties; }
    public record Decision(FeatureMode featureMode, Confidence confidence, int evidenceCount,
                           int requiredEvidenceCount, int supportingEvidenceCount,
                           List<EvidenceFlag> flags, List<Reason> exclusionReasons) {
        public Decision { flags=List.copyOf(flags); exclusionReasons=List.copyOf(exclusionReasons); }
        public boolean allowed() { return exclusionReasons.isEmpty(); }
    }
    private record Evidence(String space,long id) {}
    private Set<Evidence> evidence(IdSets sets) {
        Set<Evidence> result=new HashSet<>();
        sets.capabilityIds().forEach(id->result.add(new Evidence("capability",id)));
        sets.techIds().forEach(id->result.add(new Evidence("tech",id)));
        return result;
    }
    private Set<Evidence> intersection(PostingSimilarityScore.CategoryScore category) {
        return evidence(new IdSets(category.capability().intersectionIds(),category.tech().intersectionIds()));
    }
    public int supportingFeatureCount(RecruitUnitFeatures target) {
        var ids=evidence(target.features(Category.PREFERRED));ids.addAll(evidence(target.features(Category.DUTIES)));
        return ids.size();
    }
    public FeatureMode mode(RecruitUnitFeatures target) {
        return target.hasRequiredFeatures() ? FeatureMode.REQUIRED : FeatureMode.FALLBACK_FEATURES;
    }
    public Decision evaluate(RecruitUnitFeatures target, PostingSimilarityScore score) {
        FeatureMode mode=mode(target);
        var required=intersection(score.category(Category.REQUIRED));
        var support=intersection(score.category(Category.PREFERRED));support.addAll(intersection(score.category(Category.DUTIES)));
        support.removeAll(required); // A repeated required ID is not additional supporting evidence.
        List<Reason> reasons=new ArrayList<>();
        if (mode==FeatureMode.FALLBACK_FEATURES) {
            if (supportingFeatureCount(target)<properties.getFallbackMinimumTargetFeatures()) reasons.add(Reason.REQUIRED_FEATURES_MISSING);
            if (support.size()<properties.getFallbackMinimumIntersection()) reasons.add(Reason.FALLBACK_INTERSECTION_TOO_LOW);
            return new Decision(mode,Confidence.LOW,support.size(),0,support.size(),
                    List.of(EvidenceFlag.LOW_CONFIDENCE),reasons);
        }
        var requiredScore=score.category(Category.REQUIRED);
        if (!score.hasRequiredOverlap()) reasons.add(Reason.NO_REQUIRED_OVERLAP);
        if (requiredScore.capability().targetCount()>0 && requiredScore.capability().coverage()<properties.getRequiredCapabilityMinCoverage())
            reasons.add(Reason.REQUIRED_CAPABILITY_COVERAGE_TOO_LOW);
        if (requiredScore.tech().targetCount()>0 && requiredScore.tech().intersectionCount()<properties.getRequiredTechMinIntersection())
            reasons.add(Reason.REQUIRED_TECH_INTERSECTION_TOO_LOW);
        boolean sparse=evidence(target.features(Category.REQUIRED)).size()==1;
        int total=required.size()+(sparse ? support.size() : 0);
        if (sparse && support.size()<properties.getSparseRequiredSupportingEvidence()) reasons.add(Reason.SPARSE_SUPPORTING_EVIDENCE_TOO_LOW);
        if (total<properties.getMinimumTotalEvidence()) reasons.add(Reason.TOTAL_EVIDENCE_TOO_LOW);
        return new Decision(mode,sparse ? Confidence.LOW : Confidence.HIGH,total,required.size(),support.size(),
                sparse ? List.of(EvidenceFlag.LOW_EVIDENCE) : List.of(),reasons);
    }
}
