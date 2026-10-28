package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(schema = "job", name = "requirement")
public class Requirement {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "item_id", nullable = false)
    private Long itemId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "capability_id", nullable = false)
    private Capability capability;

    // 능력이 '기타'일 때만 채워진다
    @Column(name = "other_name", nullable = false)
    private String otherName;

    // 예시/택1/모두/능력만
    @Column(nullable = false)
    private String relation;

    protected Requirement() {
    }

    public Long getId() {
        return id;
    }

    public Long getItemId() {
        return itemId;
    }

    public Capability getCapability() {
        return capability;
    }

    public String getOtherName() {
        return otherName;
    }

    public String getRelation() {
        return relation;
    }
}
