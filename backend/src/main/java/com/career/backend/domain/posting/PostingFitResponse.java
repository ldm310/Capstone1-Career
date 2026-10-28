package com.career.backend.domain.posting;

import com.career.backend.domain.profile.SkillLevel;

import java.util.List;

// 공고가 요구하는 역량마다 사용자의 확정 점수와 LV를 붙인 결과
public record PostingFitResponse(
        Long postingId,
        String companyName,
        String title,
        Long userId,
        boolean analyzed,
        List<UnitFitResponse> recruitUnits
) {

    public record UnitFitResponse(
            Long unitId,
            String name,
            String career,
            String yearsText,
            List<CapabilityFitResponse> required,
            List<CapabilityFitResponse> preferred
    ) {
    }

    public record CapabilityFitResponse(
            Long capabilityId,
            String capabilityName,
            String otherName,
            List<String> techs,
            List<String> sourceTexts,
            boolean evaluated,
            // 평가된 적 없으면 null
            Integer userScore,
            SkillLevel userLevel
    ) {
    }
}
