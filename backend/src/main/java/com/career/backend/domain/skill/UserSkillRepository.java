package com.career.backend.domain.skill;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface UserSkillRepository extends JpaRepository<UserSkill, Long> {

    List<UserSkill> findByUser_Id(Long userId);

    Optional<UserSkill> findByUser_IdAndSkill_Id(
            Long userId,
            Long skillId
    );
}