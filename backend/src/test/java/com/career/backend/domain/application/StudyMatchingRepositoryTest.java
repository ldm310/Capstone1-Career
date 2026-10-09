package com.career.backend.domain.application;

import com.career.backend.domain.job.JobPosting;
import com.career.backend.domain.job.JobPostingRepository;
import com.career.backend.domain.skill.SkillLevel;
import com.career.backend.domain.study.StudyBand;
import com.career.backend.domain.study.StudyBandCalculator;
import com.career.backend.domain.user.User;
import com.career.backend.domain.user.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class StudyMatchingRepositoryTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private JobPostingRepository jobPostingRepository;

    @Autowired
    private JobApplicationRepository jobApplicationRepository;

    @Test
    void 같은_공고의_같은_수준_지원자만_조회한다() {
        User user1 = userRepository.save(
                new User("user1@test.com", "사용자1")
        );

        User user2 = userRepository.save(
                new User("user2@test.com", "사용자2")
        );

        User user3 = userRepository.save(
                new User("user3@test.com", "사용자3")
        );

        JobPosting jobPosting = jobPostingRepository.save(
                new JobPosting(
                        "posting-1",
                        "TEST",
                        "Career 회사",
                        "주니어 백엔드 개발자",
                        "https://example.com/jobs/1"
                )
        );

        saveApplication(
                user1,
                jobPosting,
                List.of(SkillLevel.LV2, SkillLevel.LV3)
        );

        saveApplication(
                user2,
                jobPosting,
                List.of(SkillLevel.LV2, SkillLevel.LV2)
        );

        JobApplication highApplication = saveApplication(
                user3,
                jobPosting,
                List.of(SkillLevel.LV4, SkillLevel.LV5)
        );

        List<JobApplication> middleMatches =
                jobApplicationRepository
                        .findByJobPosting_IdAndStudyBandAndStudyMatchingConsentTrue(
                                jobPosting.getId(),
                                StudyBand.MIDDLE
                        );

        assertEquals(2, middleMatches.size());

        assertTrue(
                middleMatches.stream()
                        .allMatch(application ->
                                application.getStudyBand()
                                        == StudyBand.MIDDLE
                        )
        );

        assertFalse(
                middleMatches.stream()
                        .anyMatch(application ->
                                application.getId()
                                        .equals(highApplication.getId())
                        )
        );
    }

    private JobApplication saveApplication(
            User user,
            JobPosting jobPosting,
            List<SkillLevel> skillLevels
    ) {
        double average =
                StudyBandCalculator.calculateAverage(skillLevels);

        StudyBand band =
                StudyBandCalculator.calculate(skillLevels);

        JobApplication application =
                new JobApplication(user, jobPosting);

        application.changeStudyMatchingConsent(true);
        application.updateStudyEvaluation(average, band);

        return jobApplicationRepository.save(application);
    }
}