package com.career.backend.domain.posting.similarity;

import java.util.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;

public record PostingSimilarityScore(String method, String version, Map<Category, CategoryScore> categories) {
    public PostingSimilarityScore { categories=Map.copyOf(categories); }
    public record SetScore(int targetCount, int candidateCount, Set<Long> intersectionIds, Double coverage) {
        public SetScore { intersectionIds=Collections.unmodifiableSet(new TreeSet<>(intersectionIds)); }
        @JsonProperty public int intersectionCount() { return intersectionIds.size(); }
        @JsonProperty public boolean comparable() { return targetCount>0; }
    }
    public record CategoryScore(SetScore capability, SetScore tech) {}
    public CategoryScore category(Category category) { return categories.get(category); }
    public boolean hasRequiredOverlap() {
        var score=category(Category.REQUIRED);
        return score.capability().intersectionCount()>0 || score.tech().intersectionCount()>0;
    }

    /** Target denominators are shared within one selection. No weighted total exists. */
    public static int compareBestFirst(PostingSimilarityScore a, PostingSimilarityScore b) {
        for (var category : Category.values()) {
            int comparison=compareCoverage(a.category(category).capability(),b.category(category).capability());
            if (comparison!=0) return comparison;
            comparison=compareCoverage(a.category(category).tech(),b.category(category).tech());
            if (comparison!=0) return comparison;
        }
        return 0;
    }
    private static int compareCoverage(SetScore a, SetScore b) {
        // An absent target axis is absent for every candidate, never a perfect match.
        return Double.compare(b.coverage()==null ? 0 : b.coverage(),a.coverage()==null ? 0 : a.coverage());
    }
}
