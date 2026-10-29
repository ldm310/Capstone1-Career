package com.career.backend.domain.application;

import com.career.backend.domain.job.*;
import com.career.backend.domain.skill.*;
import com.career.backend.domain.study.StudyBand;
import com.career.backend.domain.user.User;
import com.career.backend.domain.user.UserRepository;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Transactional
class ApplicationSkillEvaluationServiceTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private SkillRepository skillRepository;

    @Autowired
    private UserSkillRepository userSkillRepository;

    @Autowired
    private JobPostingRepository jobPostingRepository;

    @Autowired
    private JobPostingSkillRepository jobPostingSkillRepository;

    @Autowired
    private JobApplicationRepository jobApplicationRepository;

    @Autowired
    private ApplicationSkillEvaluationService evaluationService;

    @Autowired
    private EntityManager entityManager;

    @Test
    void 공고의_필수_기술을_기준으로_사용자_수준을_평가한다() {
        User user = userRepository.save(
                new User("evaluation@test.com", "평가사용자")
        );

        Skill java = skillRepository.save(
                new Skill("Java", "java", "LANGUAGE")
        );

        Skill springBoot = skillRepository.save(
                new Skill(
                        "Spring Boot",
                        "spring-boot",
                        "FRAMEWORK"
                )
        );

        Skill docker = skillRepository.save(
                new Skill("Docker", "docker", "DEVOPS")
        );

        userSkillRepository.save(
                new UserSkill(user, java, SkillLevel.LV3)
        );

        userSkillRepository.save(
                new UserSkill(user, springBoot, SkillLevel.LV2)
        );

        JobPosting jobPosting = jobPostingRepository.save(
                new JobPosting(
                        "evaluation-posting",
                        "TEST",
                        "Career 회사",
                        "주니어 백엔드 개발자",
                        "https://example.com/jobs/evaluation"
                )
        );

        jobPostingSkillRepository.save(
                new JobPostingSkill(
                        jobPosting,
                        java,
                        RequirementType.REQUIRED,
                        "Java 개발 경험",
                        null
                )
        );

        jobPostingSkillRepository.save(
                new JobPostingSkill(
                        jobPosting,
                        springBoot,
                        RequirementType.REQUIRED,
                        "Spring Boot 프로젝트 경험",
                        null
                )
        );

        jobPostingSkillRepository.save(
                new JobPostingSkill(
                        jobPosting,
                        docker,
                        RequirementType.REQUIRED,
                        "Docker 사용 경험",
                        null
                )
        );

        JobApplication application =
                jobApplicationRepository.save(
                        new JobApplication(user, jobPosting)
                );

        ApplicationEvaluationResult result =
                evaluationService.evaluate(application.getId());

        assertEquals(3, result.requiredSkillCount());
        assertEquals(
                7.0 / 3.0,
                result.averageSkillScore(),
                0.001
        );
        assertEquals(StudyBand.MIDDLE, result.studyBand());

        entityManager.flush();
        entityManager.clear();

        JobApplication savedApplication =
                jobApplicationRepository
                        .findById(application.getId())
                        .orElseThrow();

        assertEquals(
                StudyBand.MIDDLE,
                savedApplication.getStudyBand()
        );

        assertEquals(
                7.0 / 3.0,
                savedApplication.getAverageSkillScore(),
                0.001
        );
    }
}