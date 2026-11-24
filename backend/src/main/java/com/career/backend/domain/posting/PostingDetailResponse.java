package com.career.backend.domain.posting;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

public record PostingDetailResponse(
        Long postingId,
        String companyName,
        String title,
        String site,
        String sitePostingNo,
        String siteJobCategory,
        String careerCondition,
        Short minYears,
        String employmentType,
        String kind,
        String status,
        LocalDate deadline,
        OffsetDateTime collectedAt,
        OffsetDateTime lastCheckedAt,
        List<PostingImageResponse> images,
        // 아직 추출(분석)되지 않은 공고면 null
        PostingAnalysisResponse analysis
) {

    public record PostingImageResponse(
            Long imageId,
            Short seq,
            String url,
            Boolean kept
    ) {
    }

    public record PostingAnalysisResponse(
            Long extractionRunId,
            String model,
            String dictVersion,
            OffsetDateTime analyzedAt,
            List<RecruitUnitResponse> recruitUnits
    ) {
    }

    public record RecruitUnitResponse(
            Long unitId,
            Short seq,
            String name,
            boolean it,
            String career,
            String yearsText,
            Short minYears,
            Short maxYears,
            List<UnitItemResponse> items
    ) {
    }

    public record UnitItemResponse(
            Long itemId,
            String category,
            Short seq,
            String text,
            String quote,
            List<RequirementResponse> requirements
    ) {
    }

    public record RequirementResponse(
            Long requirementId,
            Long capabilityId,
            String capabilityName,
            String otherName,
            String relation,
            List<RequirementTechResponse> techs
    ) {
    }

    public record RequirementTechResponse(
            // 사전에 없는 기술이면 null
            Long techId,
            String techName,
            String writtenName
    ) {
    }
}
