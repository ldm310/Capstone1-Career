package com.career.backend.domain.application;

import com.career.backend.domain.study.StudyBand;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface JobApplicationRepository
        extends JpaRepository<JobApplication, Long> {

    Optional<JobApplication> findByUser_IdAndJobPosting_Id(
            Long userId,
            Long jobPostingId
    );

    List<JobApplication>
    findByJobPosting_IdAndStudyBandAndStudyMatchingConsentTrue(
            Long jobPostingId,
            StudyBand studyBand
    );
}