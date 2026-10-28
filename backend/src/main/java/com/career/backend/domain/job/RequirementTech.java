package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(schema = "job", name = "requirement_tech")
public class RequirementTech {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "requirement_id", nullable = false)
    private Long requirementId;

    // 사전에 없는 기술이면 null
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "tech_id")
    private Tech tech;

    @Column(name = "written_name", nullable = false)
    private String writtenName;

    protected RequirementTech() {
    }

    public Long getId() {
        return id;
    }

    public Long getRequirementId() {
        return requirementId;
    }

    public Tech getTech() {
        return tech;
    }

    public String getWrittenName() {
        return writtenName;
    }
}
