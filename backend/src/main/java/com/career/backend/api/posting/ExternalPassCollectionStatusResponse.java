package com.career.backend.api.posting;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.OffsetDateTime;
import java.util.List;

@Schema(description="읽기 전용 합격자료 수집 상태. LOW는 참고 자료이며 기술 보유·합격 확률을 뜻하지 않습니다.")
public record ExternalPassCollectionStatusResponse(
        long postingId,long recruitUnitId,String candidateSelectionStatus,
        @Schema(allowableValues={"NOT_REQUESTED","PENDING","RUNNING","READY","INSUFFICIENT","FAILED"}) String collectionStatus,
        String source,int selectedCandidateCount,int highCandidateCount,int lowCandidateCount,
        int requestedCompanyCount,int readyCompanyCount,int materialCount,
        OffsetDateTime lastRequestedAt,OffsetDateTime startedAt,OffsetDateTime completedAt,
        boolean retryable,String safeErrorCode,String userMessage,String policyVersion,List<Candidate> candidates) {
    public ExternalPassCollectionStatusResponse { candidates=List.copyOf(candidates); }
    public record Candidate(long companyId,long candidatePostingId,long candidateRecruitUnitId,
            String standardRoleCode,String confidence,String collectionStatus,int materialCount,
            boolean reused,String relationType) {}
}
