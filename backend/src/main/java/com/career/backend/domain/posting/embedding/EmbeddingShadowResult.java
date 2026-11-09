package com.career.backend.domain.posting.embedding;

public record EmbeddingShadowResult(String status,String model,String policyVersion,
        Double required,Double preferred,Double duties,int matchedCount) {
    public static EmbeddingShadowResult unavailable(String status,String model) {
        return new EmbeddingShadowResult(status,model,EmbeddingShadowProperties.POLICY_VERSION,null,null,null,0);
    }
}
