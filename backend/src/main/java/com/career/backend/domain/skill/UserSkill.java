package com.career.backend.domain.skill;

import com.career.backend.domain.user.User;
import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(
        name = "user_skills",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_user_skill",
                        columnNames = {"user_id", "skill_id"}
                )
        }
)
public class UserSkill {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "skill_id", nullable = false)
    private Skill skill;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private SkillLevel level;

    @Column(nullable = false)
    private LocalDateTime evaluatedAt;

    protected UserSkill() {
    }

    public UserSkill(User user, Skill skill, SkillLevel level) {
        this.user = user;
        this.skill = skill;
        this.level = level;
    }

    @PrePersist
    private void prePersist() {
        this.evaluatedAt = LocalDateTime.now();
    }

    public void updateLevel(SkillLevel level) {
        this.level = level;
        this.evaluatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public User getUser() {
        return user;
    }

    public Skill getSkill() {
        return skill;
    }

    public SkillLevel getLevel() {
        return level;
    }

    public LocalDateTime getEvaluatedAt() {
        return evaluatedAt;
    }
}