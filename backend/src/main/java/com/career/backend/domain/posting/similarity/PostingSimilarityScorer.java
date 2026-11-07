package com.career.backend.domain.posting.similarity;

/** Extension point for scoring implementations; eligibility and tier policy stay in the service. */
public interface PostingSimilarityScorer {
    PostingSimilarityScore score(RecruitUnitFeatures target, RecruitUnitFeatures candidate);
}
