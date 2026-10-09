package com.career.backend.domain.application;

import com.career.backend.domain.job.JobPosting;
import com.career.backend.domain.study.StudyBand;
import com.career.backend.domain.user.User;
import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(
        name = "applications",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_application_user_job",
                        columnNames = {"user_id", "job_posting_id"}
                )
        }
)
public class JobApplication {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "job_posting_id", nullable = false)
    private JobPosting jobPosting;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private ApplicationStatus status;

    @Column(nullable = false)
    private LocalDateTime appliedAt;

    @Column(nullable = false)
    private boolean studyMatchingConsent;

    private Double averageSkillScore;

    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private StudyBand studyBand;

    private LocalDateTime evaluatedAt;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected JobApplication() {
    }

    public JobApplication(User user, JobPosting jobPosting) {
        this.user = user;
        this.jobPosting = jobPosting;
        this.status = ApplicationStatus.APPLIED;
        this.appliedAt = LocalDateTime.now();
        this.studyMatchingConsent = false;
    }

    @PrePersist
    private void prePersist() {
        this.createdAt = LocalDateTime.now();
    }

    public void updateStatus(ApplicationStatus status) {
        this.status = status;
    }

    public void changeStudyMatchingConsent(boolean consent) {
        this.studyMatchingConsent = consent;
    }

    public void updateStudyEvaluation(
            double averageSkillScore,
            StudyBand studyBand
    ) {
        this.averageSkillScore = averageSkillScore;
        this.studyBand = studyBand;
        this.evaluatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public User getUser() {
        return user;
    }

    public JobPosting getJobPosting() {
        return jobPosting;
    }

    public ApplicationStatus getStatus() {
        return status;
    }

    public LocalDateTime getAppliedAt() {
        return appliedAt;
    }

    public boolean isStudyMatchingConsent() {
        return studyMatchingConsent;
    }

    public Double getAverageSkillScore() {
        return averageSkillScore;
    }

    public StudyBand getStudyBand() {
        return studyBand;
    }

    public LocalDateTime getEvaluatedAt() {
        return evaluatedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}