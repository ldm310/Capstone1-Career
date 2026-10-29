package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface JobPostingSkillRepository
        extends JpaRepository<JobPostingSkill, Long> {

    List<JobPostingSkill>
    findByJobPosting_IdAndRequirementType(
            Long jobPostingId,
            RequirementType requirementType
    );
}