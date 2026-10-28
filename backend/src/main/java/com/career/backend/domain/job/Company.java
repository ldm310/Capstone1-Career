package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

// job 스키마는 채용공고 파이프라인이 채우는 표라서 백엔드는 읽기만 한다.
@Entity
@Immutable
@Table(schema = "job", name = "company")
public class Company {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    protected Company() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
