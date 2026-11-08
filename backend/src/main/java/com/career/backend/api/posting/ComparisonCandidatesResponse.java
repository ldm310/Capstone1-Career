package com.career.backend.api.posting;

import com.fasterxml.jackson.annotation.JsonInclude;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** API-owned DTOs. Domain records/enums and raw exclusion records are never serialized directly. */
@JsonInclude(JsonInclude.Include.ALWAYS)
@Schema(description="합격자료 비교를 위한 참고 후보. 취업 추천·합격 가능성·검증된 유사도/정확도를 의미하지 않습니다.")
public record ComparisonCandidatesResponse(
        long postingId, long recruitUnitId,
        @Schema(allowableValues={"SELECTED","NO_CANDIDATES","NOT_COMPARABLE"}) String selectionStatus,
        String reason,
        @Schema(description="1위 후보 기준. HIGH: 필수 기준을 통과한 참고 후보. LOW: 근거가 적거나 우대·업무 기반 참고 후보. 후보 없으면 null.",
                allowableValues={"HIGH","LOW"},nullable=true) String confidence,
        @Schema(allowableValues={"REQUIRED","FALLBACK_FEATURES"},nullable=true) String featureMode,
        @Schema(nullable=true) String roleCode,
        @Schema(allowableValues={"RECRUIT_UNIT_NAME","POSTING_CATEGORY","POSTING_TITLE","UNKNOWN"}) String roleResolutionSource,
        @Schema(description="1위 후보의 고유 표준 ID 근거 수. 후보가 없으면 0.") int evidenceCount,
        @Schema(description="후보가 없는 경우 대상 사유 및 후보 탈락 사유의 중복 제거 목록.") List<String> exclusionReasons,
        String policyVersion, String taxonomyVersion, AppliedCriteria appliedCriteria, List<Candidate> candidates) {
    public ComparisonCandidatesResponse { exclusionReasons=List.copyOf(exclusionReasons);candidates=List.copyOf(candidates); }

    public record AppliedCriteria(int maxCompanies,int maxPostingsPerCompany,int maxPostings,
            boolean jobFamilyExpansionEnabled,double requiredCapabilityMinCoverage,int requiredTechMinIntersection,
            int minimumTotalEvidence,int sparseRequiredSupportingEvidence,int fallbackMinimumTargetFeatures,
            int fallbackMinimumIntersection) {}
    public record IntersectionIds(List<Long> capabilityIds,List<Long> techIds) {
        public IntersectionIds { capabilityIds=List.copyOf(capabilityIds);techIds=List.copyOf(techIds); }
    }
    public record Intersections(IntersectionIds required,IntersectionIds preferred,IntersectionIds duties) {}

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record Candidate(int rank,long postingId,long companyId,String companyName,String postingTitle,
            long recruitUnitId,String recruitUnitName,
            @Schema(description="HIGH: 필수 기준을 통과한 참고 후보. LOW: 근거가 적거나 우대·업무 기반 참고 후보.",
                    allowableValues={"HIGH","LOW"}) String confidence,
            @Schema(allowableValues={"REQUIRED","FALLBACK_FEATURES"}) String featureMode,
            int evidenceCount,int requiredEvidenceCount,int supportingEvidenceCount,
            @Schema(nullable=true,description="필수 capability 교집합/대상 수. 계산 불가 시 null.") Double requiredCapabilityCoverage,
            @Schema(nullable=true) Double requiredTechCoverage,
            @Schema(nullable=true) Double preferredCapabilityCoverage,
            @Schema(nullable=true) Double preferredTechCoverage,
            @Schema(nullable=true) Double dutiesCapabilityCoverage,
            @Schema(nullable=true) Double dutiesTechCoverage,
            Intersections intersections,List<String> evidenceFlags) {
        public Candidate { evidenceFlags=List.copyOf(evidenceFlags); }
    }
}
