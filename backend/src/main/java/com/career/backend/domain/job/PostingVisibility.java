package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

/** Read-only web publication override; extraction review results stay separate. */
@Entity
@Immutable
@Table(schema = "public", name = "career_posting_visibility")
public class PostingVisibility {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "posting_id", nullable = false)
    private Long postingId;
    @Column(nullable = false)
    private String namespace;
    @Column(nullable = false)
    private boolean hidden;
    protected PostingVisibility() {}
}
