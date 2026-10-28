package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Collection;
import java.util.List;

public interface RequirementRepository
        extends JpaRepository<Requirement, Long> {

    @Query("""
            select r from Requirement r
            join fetch r.capability
            where r.itemId in :itemIds
            order by r.id
            """)
    List<Requirement> findWithCapabilityByItemIdIn(Collection<Long> itemIds);
}
