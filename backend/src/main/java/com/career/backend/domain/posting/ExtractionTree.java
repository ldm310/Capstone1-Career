package com.career.backend.domain.posting;

import com.career.backend.domain.job.*;

import java.util.List;
import java.util.Map;

// 공고의 현재 추출 결과(모집 단위 → 항목 → 요건 → 요건 기술)를 한 번에 읽어 둔 것
record ExtractionTree(
        ExtractionRun run,
        List<RecruitUnit> units,
        Map<Long, List<UnitItem>> itemsByUnitId,
        Map<Long, List<Requirement>> requirementsByItemId,
        Map<Long, List<RequirementTech>> techsByRequirementId
) {

    List<UnitItem> itemsOf(RecruitUnit unit) {
        return itemsByUnitId.getOrDefault(unit.getId(), List.of());
    }

    List<Requirement> requirementsOf(UnitItem item) {
        return requirementsByItemId.getOrDefault(item.getId(), List.of());
    }

    List<RequirementTech> techsOf(Requirement requirement) {
        return techsByRequirementId.getOrDefault(requirement.getId(), List.of());
    }
}
