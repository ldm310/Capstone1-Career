package com.career.backend.domain.profile;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface UserSkillEvaluationRepository
        extends JpaRepository<UserSkillEvaluation, Long> {

    @Query("""
            select e from UserSkillEvaluation e
            join fetch e.capability
            where e.project.id = :projectId
            order by e.capability.name
            """)
    List<UserSkillEvaluation> findWithCapabilityByProjectId(Long projectId);

    @Query("""
            select e from UserSkillEvaluation e
            join fetch e.capability
            join fetch e.project p
            where p.user.id = :userId
            """)
    List<UserSkillEvaluation> findAllByUserId(Long userId);
}
