package com.career.backend.domain.job;

import com.career.backend.domain.skill.Skill;
import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(
        name = "job_posting_skills",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_job_posting_skill_type",
                        columnNames = {
                                "job_posting_id",
                                "skill_id",
                                "requirement_type"
                        }
                )
        }
)
public class JobPostingSkill {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "job_posting_id", nullable = false)
    private JobPosting jobPosting;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "skill_id", nullable = false)
    private Skill skill;

    @Enumerated(EnumType.STRING)
    @Column(name = "requirement_type", nullable = false, length = 20)
    private RequirementType requirementType;

    @Column(nullable = false, length = 2000)
    private String rawText;

    @Column(length = 100)
    private String alternativeGroup;

    @Column(nullable = false)
    private double weight;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected JobPostingSkill() {
    }

    public JobPostingSkill(
            JobPosting jobPosting,
            Skill skill,
            RequirementType requirementType,
            String rawText,
            String alternativeGroup
    ) {
        this.jobPosting = jobPosting;
        this.skill = skill;
        this.requirementType = requirementType;
        this.rawText = rawText;
        this.alternativeGroup = alternativeGroup;
        this.weight = 1.0;
    }

    @PrePersist
    private void prePersist() {
        this.createdAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public JobPosting getJobPosting() {
        return jobPosting;
    }

    public Skill getSkill() {
        return skill;
    }

    public RequirementType getRequirementType() {
        return requirementType;
    }

    public String getRawText() {
        return rawText;
    }

    public String getAlternativeGroup() {
        return alternativeGroup;
    }

    public double getWeight() {
        return weight;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void changeWeight(double weight) {
        this.weight = weight;
    }
}