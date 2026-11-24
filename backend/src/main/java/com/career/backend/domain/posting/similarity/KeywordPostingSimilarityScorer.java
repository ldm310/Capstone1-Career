package com.career.backend.domain.posting.similarity;

import org.springframework.stereotype.Component;
import java.util.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;

@Component
public class KeywordPostingSimilarityScorer implements PostingSimilarityScorer {
    @Override
    public PostingSimilarityScore score(RecruitUnitFeatures target, RecruitUnitFeatures candidate) {
        var scores=new EnumMap<Category,PostingSimilarityScore.CategoryScore>(Category.class);
        for (var category : Category.values()) {
            var a=target.features(category); var b=candidate.features(category);
            scores.put(category,new PostingSimilarityScore.CategoryScore(
                    compare(a.capabilityIds(),b.capabilityIds()),compare(a.techIds(),b.techIds())));
        }
        return new PostingSimilarityScore("KEYWORD","1",scores);
    }
    private PostingSimilarityScore.SetScore compare(Set<Long> target, Set<Long> candidate) {
        Set<Long> intersection=new TreeSet<>(target); intersection.retainAll(candidate);
        return new PostingSimilarityScore.SetScore(target.size(),candidate.size(),intersection,
                target.isEmpty() ? null : (double)intersection.size()/target.size());
    }
}
