package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface RecruitUnitRepository
        extends JpaRepository<RecruitUnit, Long> {

    List<RecruitUnit> findByRunIdOrderBySeq(Long runId);
}
