package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface CapabilityRepository extends JpaRepository<Capability, Long> {

    List<Capability> findByActiveTrueOrderByGroupNameAscNameAsc();
}
