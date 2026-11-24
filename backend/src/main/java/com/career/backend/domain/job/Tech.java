package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(schema = "public", name = "tech")
public class Tech {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    // Existing PostgreSQL text[] column; no schema change.
    @org.hibernate.annotations.JdbcTypeCode(org.hibernate.type.SqlTypes.ARRAY)
    @Column(name = "aliases")
    private String[] aliases;

    protected Tech() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public java.util.List<String> getAliases() {
        return aliases == null ? java.util.List.of() : java.util.Arrays.stream(aliases)
                .filter(java.util.Objects::nonNull).toList();
    }
}
