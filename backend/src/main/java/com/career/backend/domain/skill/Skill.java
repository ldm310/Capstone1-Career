package com.career.backend.domain.skill;

import jakarta.persistence.*;

@Entity
@Table(
        name = "skills",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_skill_normalized_name",
                        columnNames = "normalized_name"
                )
        }
)
public class Skill {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(name = "normalized_name", nullable = false, length = 100)
    private String normalizedName;

    @Column(length = 50)
    private String category;

    protected Skill() {
    }

    public Skill(String name, String normalizedName, String category) {
        this.name = name;
        this.normalizedName = normalizedName;
        this.category = category;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getNormalizedName() {
        return normalizedName;
    }

    public String getCategory() {
        return category;
    }
}