package com.career.backend.domain.application;

import com.career.backend.domain.job.JobPostingSkill;
import com.career.backend.domain.job.JobPostingSkillRepository;
import com.career.backend.domain.job.RequirementType;
import com.career.backend.domain.skill.SkillLevel;
import com.career.backend.domain.skill.UserSkillRepository;
import com.career.backend.domain.study.StudyBand;
import com.career.backend.domain.study.StudyBandCalculator;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class ApplicationSkillEvaluationService {

    private final JobApplicationRepository jobApplicationRepository;
    private final JobPostingSkillRepository jobPostingSkillRepository;
    private final UserSkillRepository userSkillRepository;

    public ApplicationSkillEvaluationService(
            JobApplicationRepository jobApplicationRepository,
            JobPostingSkillRepository jobPostingSkillRepository,
            UserSkillRepository userSkillRepository
    ) {
        this.jobApplicationRepository = jobApplicationRepository;
        this.jobPostingSkillRepository = jobPostingSkillRepository;
        this.userSkillRepository = userSkillRepository;
    }

    @Transactional
    public ApplicationEvaluationResult evaluate(Long applicationId) {
        JobApplication application =
                jobApplicationRepository.findById(applicationId)
                        .orElseThrow(() ->
                                new IllegalArgumentException(
                                        "지원 기록을 찾을 수 없습니다."
                                )
                        );

        List<JobPostingSkill> requiredSkills =
                jobPostingSkillRepository
                        .findByJobPosting_IdAndRequirementType(
                                application.getJobPosting().getId(),
                                RequirementType.REQUIRED
                        );

        if (requiredSkills.isEmpty()) {
            throw new IllegalStateException(
                    "공고에 등록된 필수 기술이 없습니다."
            );
        }

        List<SkillLevel> userLevels = requiredSkills.stream()
                .map(jobSkill ->
                        findUserSkillLevel(
                                application.getUser().getId(),
                                jobSkill
                        )
                )
                .toList();

        double averageScore =
                StudyBandCalculator.calculateAverage(userLevels);

        StudyBand studyBand =
                StudyBandCalculator.calculate(userLevels);

        application.updateStudyEvaluation(
                averageScore,
                studyBand
        );

        return new ApplicationEvaluationResult(
                application.getId(),
                requiredSkills.size(),
                averageScore,
                studyBand
        );
    }

    private SkillLevel findUserSkillLevel(
            Long userId,
            JobPostingSkill jobPostingSkill
    ) {
        return userSkillRepository
                .findByUser_IdAndSkill_Id(
                        userId,
                        jobPostingSkill.getSkill().getId()
                )
                .map(userSkill -> userSkill.getLevel())
                .orElse(SkillLevel.UNASSESSED);
    }
}