package com.career.backend.domain.profile;

import java.time.OffsetDateTime;

public record ProjectResponse(
        Long projectId,
        Long userId,
        String projectName,
        String repositoryUrl,
        boolean hasDescriptionFile,
        String descriptionFileType,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt
) {

    public static ProjectResponse from(Project project) {
        return new ProjectResponse(
                project.getId(),
                project.getUser().getId(),
                project.getProjectName(),
                project.getRepositoryUrl(),
                project.getDescriptionFilePath() != null,
                project.getDescriptionFileType(),
                project.getCreatedAt(),
                project.getUpdatedAt()
        );
    }
}
