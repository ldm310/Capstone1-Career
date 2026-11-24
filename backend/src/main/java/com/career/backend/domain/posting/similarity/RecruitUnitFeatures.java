package com.career.backend.domain.posting.similarity;

import java.util.*;

/** ID-only comparison features. No posting body, quotes or company names. */
public record RecruitUnitFeatures(long postingId, long companyId, long runId, long unitId,
        String unitName, String postingCategory, String postingTitle,
        Map<Category, IdSets> categories) {
    public enum Category { REQUIRED, PREFERRED, DUTIES }

    public record IdSets(Set<Long> capabilityIds, Set<Long> techIds) {
        public IdSets {
            capabilityIds = Set.copyOf(capabilityIds);
            techIds = Set.copyOf(techIds);
        }
        public static IdSets empty() { return new IdSets(Set.of(), Set.of()); }
    }

    public RecruitUnitFeatures {
        var copy = new EnumMap<Category, IdSets>(Category.class);
        for (var category : Category.values()) copy.put(category, categories.getOrDefault(category, IdSets.empty()));
        categories = Collections.unmodifiableMap(copy);
    }

    public IdSets features(Category category) { return categories.get(category); }
    public boolean hasRequiredFeatures() {
        var required = features(Category.REQUIRED);
        return !required.capabilityIds().isEmpty() || !required.techIds().isEmpty();
    }
}
