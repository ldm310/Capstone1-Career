package com.career.backend.api.posting;

/** Synthetic, compile-time OpenAPI examples, not actual source records. */
final class ComparisonCandidatesExamples {
    private ComparisonCandidatesExamples() {}
    static final String CRITERIA="""
            "appliedCriteria":{"maxCompanies":3,"maxPostingsPerCompany":2,"maxPostings":5,"jobFamilyExpansionEnabled":false,
            "requiredCapabilityMinCoverage":0.5,"requiredTechMinIntersection":1,"minimumTotalEvidence":2,
            "sparseRequiredSupportingEvidence":1,"fallbackMinimumTargetFeatures":2,"fallbackMinimumIntersection":2}
            """;
    static final String COMMON="""
            "postingId":1,"recruitUnitId":11,"roleCode":"backend","roleResolutionSource":"RECRUIT_UNIT_NAME",
            "policyVersion":"keyword-mvp-2","taxonomyVersion":"roles-mvp-2",
            """;
    static final String CANDIDATE="""
            "rank":1,"postingId":3,"companyId":2,"companyName":"예시 기업","postingTitle":"백엔드 개발",
            "recruitUnitId":31,"recruitUnitName":"백엔드 개발자",
            "embeddingStatus":"NOT_GENERATED","embeddingModel":"text-embedding-3-small","embeddingPolicyVersion":"semantic-shadow-v1",
            "requiredSemanticSimilarity":null,"preferredSemanticSimilarity":null,"dutiesSemanticSimilarity":null,"semanticMatchedRequirementCount":0,
            """;
    static final String SELECTED="{"+COMMON+CRITERIA+","+"""
            "selectionStatus":"SELECTED","reason":"NONE","confidence":"HIGH","featureMode":"REQUIRED",
            "evidenceCount":2,"exclusionReasons":[],"candidates":[{
            """+CANDIDATE+"""
            "confidence":"HIGH","featureMode":"REQUIRED","evidenceCount":2,"requiredEvidenceCount":2,"supportingEvidenceCount":0,
            "requiredCapabilityCoverage":1.0,"requiredTechCoverage":0.5,"preferredCapabilityCoverage":null,"preferredTechCoverage":null,
            "dutiesCapabilityCoverage":null,"dutiesTechCoverage":null,"intersections":{"required":{"capabilityIds":[1],"techIds":[10]},
            "preferred":{"capabilityIds":[],"techIds":[]},"duties":{"capabilityIds":[],"techIds":[]}},"evidenceFlags":[]}]}
            """;
    static final String LOW="{"+COMMON+CRITERIA+","+"""
            "selectionStatus":"SELECTED","reason":"NONE","confidence":"LOW","featureMode":"FALLBACK_FEATURES",
            "evidenceCount":2,"exclusionReasons":[],"candidates":[{
            """+CANDIDATE+"""
            "confidence":"LOW","featureMode":"FALLBACK_FEATURES","evidenceCount":2,"requiredEvidenceCount":0,"supportingEvidenceCount":2,
            "requiredCapabilityCoverage":null,"requiredTechCoverage":null,"preferredCapabilityCoverage":1.0,"preferredTechCoverage":1.0,
            "dutiesCapabilityCoverage":null,"dutiesTechCoverage":null,"intersections":{"required":{"capabilityIds":[],"techIds":[]},
            "preferred":{"capabilityIds":[1],"techIds":[10]},"duties":{"capabilityIds":[],"techIds":[]}},"evidenceFlags":["LOW_CONFIDENCE"]}]}
            """;
    static final String NO_CANDIDATES="{"+COMMON+CRITERIA+","+"""
            "selectionStatus":"NO_CANDIDATES","reason":"NO_ELIGIBLE_CANDIDATE","confidence":null,"featureMode":"REQUIRED",
            "evidenceCount":0,"exclusionReasons":["NO_ELIGIBLE_CANDIDATE","REQUIRED_TECH_INTERSECTION_TOO_LOW"],"candidates":[]}
            """;
    static final String NOT_COMPARABLE="{"+COMMON+CRITERIA+","+"""
            "selectionStatus":"NOT_COMPARABLE","reason":"REQUIRED_FEATURES_MISSING","confidence":null,"featureMode":"FALLBACK_FEATURES",
            "evidenceCount":0,"exclusionReasons":["REQUIRED_FEATURES_MISSING"],"candidates":[]}
            """;
}
