package com.career.backend.domain.external;

import com.career.backend.domain.common.PageResponse;
import java.time.OffsetDateTime;

public record ExternalPassMaterialResponse(Long postingId, Long companyId, CollectionInfo collection,
                                           PageResponse<MaterialInfo> materials) {
    public record CollectionInfo(Long companyId, CollectionStatus status, int minimumSampleSize, int attemptCount,
                                 OffsetDateTime requestedAt, OffsetDateTime startedAt,
                                 OffsetDateTime completedAt, OffsetDateTime updatedAt, String errorCode) {
        static CollectionInfo from(CompanyCollection c) {
            return new CollectionInfo(c.getCompanyId(), c.getStatus(), c.getMinimumSampleSize(), c.getAttemptCount(),
                    c.getRequestedAt(), c.getStartedAt(), c.getCompletedAt(), c.getUpdatedAt(), c.getErrorCode());
        }
    }
    public record MaterialInfo(Long materialId, Long companyId, String sourcePlatform, String externalRecordId,
                               String jobFamily, String roleName, String title, String content, String sourceUrl,
                               OffsetDateTime publishedAt, OffsetDateTime collectedAt, OffsetDateTime updatedAt,
                               MaterialRelationType relationType) {
        static MaterialInfo from(PostingPassMaterial link) {
            var m = link.getMaterial();
            return new MaterialInfo(m.getId(), m.getCompanyId(), m.getSourcePlatform(), m.getExternalRecordId(),
                    m.getJobFamily(), m.getRoleName(), m.getTitle(), m.getContent(), m.getSourceUrl(),
                    m.getPublishedAt(), m.getCollectedAt(), m.getUpdatedAt(), link.getRelationType());
        }
    }
}
