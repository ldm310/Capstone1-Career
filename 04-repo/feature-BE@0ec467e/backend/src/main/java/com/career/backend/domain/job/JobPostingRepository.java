package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface JobPostingRepository
        extends JpaRepository<JobPosting, Long> {

    List<JobPosting> findByStatus(JobPostingStatus status);

    List<JobPosting> findByCompanyNameContainingIgnoreCase(
            String companyName
    );
}