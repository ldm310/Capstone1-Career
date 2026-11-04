package com.career.backend.domain.external;

import java.util.List;

/** Keyword mentions in source materials; neither verified skill possession nor a reason for acceptance. */
public record ExternalPassKeywordResponse(Long postingId, int sourceMaterialCount,
        List<KeywordCount> requiredOverlap, List<KeywordCount> preferredOverlap,
        List<KeywordCount> externalOnly, List<String> unmappedKeywords) {
    public record KeywordCount(Long techId, String name, int materialCount) {}
}
