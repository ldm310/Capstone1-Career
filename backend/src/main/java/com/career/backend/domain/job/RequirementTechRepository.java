package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Collection;
import java.util.List;

public interface RequirementTechRepository
        extends JpaRepository<RequirementTech, Long> {

    interface PostingTech {
        String getCategory();
        Long getTechId();
    }

    @Query("""
            select distinct item.category as category, tech.id as techId
            from RequirementTech rt join rt.tech tech,
                 Requirement requirement, UnitItem item, RecruitUnit unit, ExtractionRun run
            where rt.requirementId = requirement.id and requirement.itemId = item.id
              and item.unitId = unit.id and unit.runId = run.id
              and run.postingId = :postingId and run.current = true
              and item.category in ('필수', '우대')
            """)
    List<PostingTech> findCurrentPostingTechs(Long postingId);

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
