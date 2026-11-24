package com.career.backend.domain.profile;

import jakarta.persistence.*;

import java.time.OffsetDateTime;

@Entity
@Table(schema = "profile", name = "project")
public class Project {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "project_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private AppUser user;

    @Column(name = "project_name", nullable = false)
    private String projectName;

    @Column(name = "repository_url")
    private String repositoryUrl;

    @Column(name = "description_file_path")
    private String descriptionFilePath;

    @Column(name = "description_file_type", length = 50)
    private String descriptionFileType;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected Project() {
    }

    public Project(
            AppUser user,
            String projectName,
            String repositoryUrl,
            String descriptionFilePath,
            String descriptionFileType
    ) {
        this.user = user;
        this.projectName = projectName;
        this.repositoryUrl = repositoryUrl;
        this.descriptionFilePath = descriptionFilePath;
        this.descriptionFileType = descriptionFileType;
    }

    @PrePersist
    private void prePersist() {
        this.createdAt = OffsetDateTime.now();
        this.updatedAt = this.createdAt;
    }

    @PreUpdate
    private void preUpdate() {
        this.updatedAt = OffsetDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public AppUser getUser() {
        return user;
    }

    public String getProjectName() {
        return projectName;
    }

    public String getRepositoryUrl() {
        return repositoryUrl;
    }

    public String getDescriptionFilePath() {
        return descriptionFilePath;
    }

    public String getDescriptionFileType() {
        return descriptionFileType;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    public OffsetDateTime getUpdatedAt() {
        return updatedAt;
    }
}
