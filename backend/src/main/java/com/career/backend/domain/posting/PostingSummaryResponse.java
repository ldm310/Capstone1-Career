package com.career.backend.domain.posting;

import com.career.backend.domain.job.Posting;

import java.time.LocalDate;

public record PostingSummaryResponse(
        Long postingId,
        String companyName,
        String title,
        String siteJobCategory,
        String careerCondition,
        String employmentType,
        String kind,
        String status,
        LocalDate deadline
) {

    public static PostingSummaryResponse from(Posting posting) {
        return new PostingSummaryResponse(
                posting.getId(),
                posting.getCompany().getName(),
                posting.getTitle(),
                posting.getSiteJobCategory(),
                posting.getCareerCondition(),
                posting.getEmploymentType(),
                posting.getKind(),
                posting.getStatus(),
                posting.getDeadline()
        );
    }
}
