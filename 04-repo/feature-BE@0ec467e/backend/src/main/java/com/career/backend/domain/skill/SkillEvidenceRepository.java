package com.career.backend.domain.skill;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface SkillEvidenceRepository
        extends JpaRepository<SkillEvidence, Long> {

    List<SkillEvidence> findByUserSkill_Id(Long userSkillId);

    List<SkillEvidence> findByUserSkill_IdAndStatus(
            Long userSkillId,
            EvidenceStatus status
    );
}