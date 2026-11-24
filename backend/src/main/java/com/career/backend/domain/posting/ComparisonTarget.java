package com.career.backend.domain.posting;

import jakarta.persistence.*;
import lombok.Getter;

/** Curated comparison metadata, independent of the immutable extraction. */
@Entity
@Getter
@Table(schema = "profile", name = "comparison_target")
public class ComparisonTarget {
    @Id @Column(name = "unit_id") private Long unitId;
    @Column(nullable = false) private String roleGroup;
    @Column(nullable = false) private String careerBand;
    protected ComparisonTarget() {}
}
