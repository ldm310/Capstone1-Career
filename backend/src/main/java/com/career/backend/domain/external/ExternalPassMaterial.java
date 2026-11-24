package com.career.backend.domain.external;

import jakarta.persistence.*;
import lombok.Getter;
import org.hibernate.annotations.Immutable;
import java.time.OffsetDateTime;

@Entity
@Immutable
@Getter
@Table(schema = "external_data", name = "pass_material",
        uniqueConstraints = @UniqueConstraint(columnNames = {"source_platform", "external_record_id"}))
public class ExternalPassMaterial {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) private Long id;
    @Column(nullable = false) private Long companyId;
    @Column(nullable = false) private String sourcePlatform;
    @Column(nullable = false) private String externalRecordId;
    @Column(nullable = false) private String jobFamily;
    @Column(nullable = false) private String roleName;
    @Column(nullable = false, columnDefinition = "text") private String title;
    @Column(nullable = false, columnDefinition = "text") private String content;
    @Column(nullable = false, columnDefinition = "text") private String sourceUrl;
    private OffsetDateTime publishedAt;
    @Column(nullable = false) private OffsetDateTime collectedAt;
    @Column(nullable = false) private OffsetDateTime updatedAt;
    protected ExternalPassMaterial() {}
}
