package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(schema = "job", name = "tech")
public class Tech {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    protected Tech() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
