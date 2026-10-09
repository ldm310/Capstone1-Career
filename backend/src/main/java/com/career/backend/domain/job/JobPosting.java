package com.career.backend.domain.job;

import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "job_postings")
public class JobPosting {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(length = 100)
    private String externalId;

    @Column(nullable = false, length = 50)
    private String source;

    @Column(nullable = false, length = 100)
    private String companyName;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(length = 100)
    private String experienceLevel;

    @Column(length = 100)
    private String location;

    @Column(length = 1000)
    private String sourceUrl;

    @Column(columnDefinition = "TEXT")
    private String rawDescription;

    private LocalDateTime openedAt;

    private LocalDateTime deadlineAt;

    @Column(length = 100)
    private String deadlineText;

    private LocalDateTime lastCheckedAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private JobPostingStatus status;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    protected JobPosting() {
    }

    public JobPosting(
            String externalId,
            String source,
            String companyName,
            String title,
            String sourceUrl
    ) {
        this.externalId = externalId;
        this.source = source;
        this.companyName = companyName;
        this.title = title;
        this.sourceUrl = sourceUrl;
        this.status = JobPostingStatus.UNKNOWN;
    }

    @PrePersist
    private void prePersist() {
        this.createdAt = LocalDateTime.now();

        if (this.lastCheckedAt == null) {
            this.lastCheckedAt = LocalDateTime.now();
        }
    }

    public Long getId() {
        return id;
    }

    public String getExternalId() {
        return externalId;
    }

    public String getSource() {
        return source;
    }

    public String getCompanyName() {
        return companyName;
    }

    public String getTitle() {
        return title;
    }

    public String getExperienceLevel() {
        return experienceLevel;
    }

    public String getLocation() {
        return location;
    }

    public String getSourceUrl() {
        return sourceUrl;
    }

    public String getRawDescription() {
        return rawDescription;
    }

    public LocalDateTime getOpenedAt() {
        return openedAt;
    }

    public LocalDateTime getDeadlineAt() {
        return deadlineAt;
    }

    public String getDeadlineText() {
        return deadlineText;
    }

    public LocalDateTime getLastCheckedAt() {
        return lastCheckedAt;
    }

    public JobPostingStatus getStatus() {
        return status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}