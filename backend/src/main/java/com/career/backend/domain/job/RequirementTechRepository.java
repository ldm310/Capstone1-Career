package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Collection;
import java.util.List;

public interface RequirementTechRepository
        extends JpaRepository<RequirementTech, Long> {

    @Query("""
            select rt from RequirementTech rt
            left join fetch rt.tech
            where rt.requirementId in :requirementIds
            order by rt.id
            """)
    List<RequirementTech> findWithTechByRequirementIdIn(
            Collection<Long> requirementIds
    );
}
