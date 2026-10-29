package com.career.backend.domain.skill;

import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "skill_evidences")
public class SkillEvidence {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_skill_id", nullable = false)
    private UserSkill userSkill;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private EvidenceSourceType sourceType;

    @Column(nullable = false, length = 255)
    private String sourceName;

    @Column(length = 1000)
    private String sourceUrl;

    @Column(length = 1000)
    private String sourceLocation;

    @Column(nullable = false, length = 5000)
    private String excerpt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private EvidenceStatus status;

    @Column(nullable = false, updatable = false)
    private LocalDateTime detectedAt;

    protected SkillEvidence() {
    }

    public SkillEvidence(
            UserSkill userSkill,
            EvidenceSourceType sourceType,
            String sourceName,
            String sourceUrl,
            String sourceLocation,
            String excerpt
    ) {
        this.userSkill = userSkill;
        this.sourceType = sourceType;
        this.sourceName = sourceName;
        this.sourceUrl = sourceUrl;
        this.sourceLocation = sourceLocation;
        this.excerpt = excerpt;
        this.status = EvidenceStatus.DETECTED;
    }

    @PrePersist
    private void prePersist() {
        this.detectedAt = LocalDateTime.now();
    }

    public void confirm() {
        this.status = EvidenceStatus.CONFIRMED;
    }

    public void reject() {
        this.status = EvidenceStatus.REJECTED;
    }

    public Long getId() {
        return id;
    }

    public UserSkill getUserSkill() {
        return userSkill;
    }

    public EvidenceSourceType getSourceType() {
        return sourceType;
    }

    public String getSourceName() {
        return sourceName;
    }

    public String getSourceUrl() {
        return sourceUrl;
    }

    public String getSourceLocation() {
        return sourceLocation;
    }

    public String getExcerpt() {
        return excerpt;
    }

    public EvidenceStatus getStatus() {
        return status;
    }

    public LocalDateTime getDetectedAt() {
        return detectedAt;
    }
}