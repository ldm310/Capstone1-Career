package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(schema = "job", name = "capability")
public class Capability {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @Column(name = "group_name")
    private String groupName;

    @Column(name = "parent_id")
    private Long parentId;

    @Column(name = "is_active", nullable = false)
    private boolean active;

    protected Capability() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getGroupName() {
        return groupName;
    }

    public Long getParentId() {
        return parentId;
    }

    public boolean isActive() {
        return active;
    }
}
