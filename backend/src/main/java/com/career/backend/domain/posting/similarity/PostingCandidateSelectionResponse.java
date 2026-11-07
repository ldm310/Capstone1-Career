package com.career.backend.domain.posting.similarity;

import java.util.List;
import static com.career.backend.domain.posting.similarity.RecruitUnitRoleResolver.RoleMatch;

public record PostingCandidateSelectionResponse(long postingId, Long companyId, Status status,
        Reason reason, String exactPostingEvidenceStatus, Policy policy, List<DataIssue> dataIssues,
        List<UnitSelection> units) {
    public PostingCandidateSelectionResponse { dataIssues=List.copyOf(dataIssues); units=List.copyOf(units); }
    public enum Status { SELECTED, NO_CANDIDATES, NOT_COMPARABLE, DATA_ERROR }
    public enum Reason {
        NONE, NO_CURRENT_EXTRACTION, NO_IT_RECRUIT_UNIT, UNKNOWN_ROLE, AMBIGUOUS_ROLE,
        NO_REQUIRED_FEATURES, NO_ELIGIBLE_CANDIDATE, NO_REQUIRED_OVERLAP, DUPLICATE_CURRENT_EXTRACTION,
        REQUIRED_FEATURES_MISSING, REQUIRED_CAPABILITY_COVERAGE_TOO_LOW, REQUIRED_TECH_INTERSECTION_TOO_LOW,
        TOTAL_EVIDENCE_TOO_LOW, SPARSE_SUPPORTING_EVIDENCE_TOO_LOW, FALLBACK_INTERSECTION_TOO_LOW
    }
    public enum Stage { EXACT_ROLE, SAME_JOB_FAMILY, NONE }
    public enum Confidence { HIGH, LOW }
    public enum FeatureMode { REQUIRED, FALLBACK_FEATURES }
    public enum EvidenceFlag { LOW_EVIDENCE, LOW_CONFIDENCE }
    public record Thresholds(double requiredCapabilityMinCoverage, int requiredTechMinIntersection,
                             int minimumTotalEvidence, int sparseRequiredSupportingEvidence,
                             int fallbackMinimumTargetFeatures, int fallbackMinimumIntersection) {}
    public record Policy(String version, int maxCompanies, int maxPostingsPerCompany, int maxPostings,
                         boolean jobFamilyExpansionEnabled, Thresholds thresholds) {}
    public record DataIssue(long postingId, int currentRunCount, Reason reason) {}
    public record Exclusion(long postingId, long unitId, Reason reason, RoleMatch role, List<Reason> exclusionReasons) {
        public Exclusion { exclusionReasons=List.copyOf(exclusionReasons); }
    }
    public record Candidate(int rank, long postingId, long companyId, long unitId, long extractionRunId,
                            Stage stage, RoleMatch role, PostingSimilarityScore score, Confidence confidence,
                            FeatureMode featureMode, int evidenceCount, int requiredEvidenceCount,
                            int supportingEvidenceCount, List<EvidenceFlag> evidenceFlags, List<Reason> exclusionReasons) {
        public Candidate { evidenceFlags=List.copyOf(evidenceFlags); exclusionReasons=List.copyOf(exclusionReasons); }
        public Candidate withRank(int rank) {
            return new Candidate(rank,postingId,companyId,unitId,extractionRunId,stage,role,score,confidence,
                    featureMode,evidenceCount,requiredEvidenceCount,supportingEvidenceCount,evidenceFlags,exclusionReasons);
        }
    }
    public record UnitSelection(long unitId, long extractionRunId, RoleMatch role, Status status, Reason reason,
                                Stage stage, boolean familyExpansionAttempted, List<Candidate> candidates,
                                List<Exclusion> exclusions, FeatureMode featureMode, List<Reason> exclusionReasons) {
        public UnitSelection { candidates=List.copyOf(candidates); exclusions=List.copyOf(exclusions); exclusionReasons=List.copyOf(exclusionReasons); }
    }
}
