package com.career.backend.domain.external;

import jakarta.persistence.*;
import lombok.Getter;
import org.hibernate.annotations.Immutable;
import java.time.OffsetDateTime;

@Entity
@Immutable
@Getter
@Table(schema = "external_data", name = "posting_pass_material",
        uniqueConstraints = @UniqueConstraint(columnNames = {"posting_id", "material_id"}))
public class PostingPassMaterial {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) private Long id;
    @Column(nullable = false) private Long postingId;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "material_id", nullable = false) private ExternalPassMaterial material;
    @Enumerated(EnumType.STRING) @Column(nullable = false) private MaterialRelationType relationType;
    @Column(nullable = false) private OffsetDateTime linkedAt;
    protected PostingPassMaterial() {}
}
