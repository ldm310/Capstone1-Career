package com.career.backend.domain.profile;

import com.career.backend.domain.job.Capability;
import jakarta.persistence.*;

import java.time.OffsetDateTime;

// 프로젝트별 능력 하나에 최신 평가 하나만 저장한다. (UNIQUE project_id, capability_id)
@Entity
@Table(
        schema = "profile",
        name = "user_skill_evaluation",
        uniqueConstraints = @UniqueConstraint(
                columnNames = {"project_id", "capability_id"}
        )
)
public class UserSkillEvaluation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "evaluation_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "capability_id", nullable = false)
    private Capability capability;

    // 0~100
    @Column(name = "confirmed_score", nullable = false)
    private Short confirmedScore;

    @Column(name = "evaluated_at", nullable = false)
    private OffsetDateTime evaluatedAt;

    protected UserSkillEvaluation() {
    }

    public UserSkillEvaluation(
            Project project,
            Capability capability,
            int confirmedScore
    ) {
        this.project = project;
        this.capability = capability;
        updateScore(confirmedScore);
    }

    public void updateScore(int confirmedScore) {
        if (confirmedScore < 0 || confirmedScore > 100) {
            throw new IllegalArgumentException(
                    "확정 역량 점수는 0~100 사이여야 합니다."
            );
        }

        this.confirmedScore = (short) confirmedScore;
        this.evaluatedAt = OffsetDateTime.now();
    }

    public SkillLevel getLevel() {
        return SkillLevel.fromScore(getConfirmedScore());
    }

    public Long getId() {
        return id;
    }

    public Project getProject() {
        return project;
    }

    public Capability getCapability() {
        return capability;
    }

    public int getConfirmedScore() {
        return confirmedScore;
    }

    public OffsetDateTime getEvaluatedAt() {
        return evaluatedAt;
    }
}
