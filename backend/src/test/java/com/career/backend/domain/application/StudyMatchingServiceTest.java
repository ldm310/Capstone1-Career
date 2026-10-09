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

@SpringBootTest
@Transactional
class StudyMatchingServiceTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private JobPostingRepository jobPostingRepository;

    @Autowired
    private JobApplicationRepository jobApplicationRepository;

    @Autowired
    private StudyMatchingService studyMatchingService;

    @Test
    void 동일_공고의_동일_수준_동의자만_추천한다() {
        User me = userRepository.save(
                new User("me@test.com", "나")
        );

        User sameLevelUser = userRepository.save(
                new User("same@test.com", "같은수준")
        );

        User highLevelUser = userRepository.save(
                new User("high@test.com", "높은수준")
        );

        User noConsentUser = userRepository.save(
                new User("no-consent@test.com", "미동의자")
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

        JobApplication myApplication = saveApplication(
                me,
                jobPosting,
                List.of(SkillLevel.LV2, SkillLevel.LV3),
                true
        );

        saveApplication(
                sameLevelUser,
                jobPosting,
                List.of(SkillLevel.LV2, SkillLevel.LV2),
                true
        );

        saveApplication(
                highLevelUser,
                jobPosting,
                List.of(SkillLevel.LV4, SkillLevel.LV5),
                true
        );

        saveApplication(
                noConsentUser,
                jobPosting,
                List.of(SkillLevel.LV2, SkillLevel.LV3),
                false
        );

        List<StudyMatchCandidate> result =
                studyMatchingService.findCandidates(
                        myApplication.getId()
                );

        assertEquals(1, result.size());
        assertEquals("같은수준", result.getFirst().nickname());
        assertEquals(StudyBand.MIDDLE, result.getFirst().studyBand());
    }

    private JobApplication saveApplication(
            User user,
            JobPosting jobPosting,
            List<SkillLevel> skillLevels,
            boolean consent
    ) {
        double average =
                StudyBandCalculator.calculateAverage(skillLevels);

        StudyBand band =
                StudyBandCalculator.calculate(skillLevels);

        JobApplication application =
                new JobApplication(user, jobPosting);

        application.changeStudyMatchingConsent(consent);
        application.updateStudyEvaluation(average, band);

        return jobApplicationRepository.save(application);
    }
}