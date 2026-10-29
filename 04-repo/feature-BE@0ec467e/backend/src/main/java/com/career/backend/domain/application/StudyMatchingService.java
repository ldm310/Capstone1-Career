package com.career.backend.domain.application;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@Transactional(readOnly = true)
public class StudyMatchingService {

    private final JobApplicationRepository jobApplicationRepository;

    public StudyMatchingService(
            JobApplicationRepository jobApplicationRepository
    ) {
        this.jobApplicationRepository = jobApplicationRepository;
    }

    public List<StudyMatchCandidate> findCandidates(
            Long applicationId
    ) {
        JobApplication myApplication =
                jobApplicationRepository.findById(applicationId)
                        .orElseThrow(() ->
                                new IllegalArgumentException(
                                        "지원 기록을 찾을 수 없습니다."
                                )
                        );

        if (!myApplication.isStudyMatchingConsent()) {
            throw new IllegalStateException(
                    "스터디 매칭에 동의해야 추천을 받을 수 있습니다."
            );
        }

        if (myApplication.getStudyBand() == null) {
            throw new IllegalStateException(
                    "아직 지원자의 역량 수준이 계산되지 않았습니다."
            );
        }

        return jobApplicationRepository
                .findByJobPosting_IdAndStudyBandAndStudyMatchingConsentTrueAndIdNot(
                        myApplication.getJobPosting().getId(),
                        myApplication.getStudyBand(),
                        myApplication.getId()
                )
                .stream()
                .map(this::toCandidate)
                .toList();
    }

    private StudyMatchCandidate toCandidate(
            JobApplication application
    ) {
        return new StudyMatchCandidate(
                application.getId(),
                application.getUser().getId(),
                application.getUser().getNickname(),
                application.getStudyBand(),
                application.getAverageSkillScore()
        );
    }
}