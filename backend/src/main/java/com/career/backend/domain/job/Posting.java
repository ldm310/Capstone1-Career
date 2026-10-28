package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

import java.time.LocalDate;
import java.time.OffsetDateTime;

@Entity
@Immutable
@Table(schema = "job", name = "posting")
public class Posting {

    public static final String OPEN = "진행";
    public static final String CLOSED = "마감";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "company_id", nullable = false)
    private Company company;

    @Column(nullable = false)
    private String site;

    @Column(name = "site_posting_no", nullable = false)
    private String sitePostingNo;

    @Column(nullable = false)
    private String title;

    @Column(name = "site_job_category")
    private String siteJobCategory;

    @Column(name = "career_condition")
    private String careerCondition;

    @Column(name = "min_years")
    private Short minYears;

    @Column(name = "employment_type")
    private String employmentType;

    // 글/이미지/섞임
    @Column(nullable = false)
    private String kind;

    // 진행/마감
    @Column(nullable = false)
    private String status;

    private LocalDate deadline;

    @Column(name = "collected_at", nullable = false)
    private OffsetDateTime collectedAt;

    @Column(name = "last_checked_at", nullable = false)
    private OffsetDateTime lastCheckedAt;

    protected Posting() {
    }

    public Long getId() {
        return id;
    }

    public Company getCompany() {
        return company;
    }

    public String getSite() {
        return site;
    }

    public String getSitePostingNo() {
        return sitePostingNo;
    }

    public String getTitle() {
        return title;
    }

    public String getSiteJobCategory() {
        return siteJobCategory;
    }

    public String getCareerCondition() {
        return careerCondition;
    }

    public Short getMinYears() {
        return minYears;
    }

    public String getEmploymentType() {
        return employmentType;
    }

    public String getKind() {
        return kind;
    }

    public String getStatus() {
        return status;
    }

    public LocalDate getDeadline() {
        return deadline;
    }

    public OffsetDateTime getCollectedAt() {
        return collectedAt;
    }

    public OffsetDateTime getLastCheckedAt() {
        return lastCheckedAt;
    }
}
