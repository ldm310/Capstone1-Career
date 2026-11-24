package com.career.backend.domain.external;

import jakarta.persistence.*;
import lombok.Getter;
import org.hibernate.annotations.Immutable;
import java.time.OffsetDateTime;

@Entity
@Immutable
@Getter
@Table(schema = "external_data", name = "company_collection")
public class CompanyCollection {
    @Id private Long companyId;
    @Enumerated(EnumType.STRING) @Column(nullable = false) private CollectionStatus status;
    @Column(nullable = false) private int minimumSampleSize;
    @Column(nullable = false) private int attemptCount;
    @Column(nullable = false) private OffsetDateTime requestedAt;
    private OffsetDateTime startedAt;
    private OffsetDateTime completedAt;
    @Column(nullable = false) private OffsetDateTime updatedAt;
    @Column(length = 100) private String errorCode;
    @Column(columnDefinition = "text") private String errorMessage;
    protected CompanyCollection() {}
}
