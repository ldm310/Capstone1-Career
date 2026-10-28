package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ExtractionRunRepository
        extends JpaRepository<ExtractionRun, Long> {

    Optional<ExtractionRun> findByPostingIdAndCurrentTrue(Long postingId);
}
