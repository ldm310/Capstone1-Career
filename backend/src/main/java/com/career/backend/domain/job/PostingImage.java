package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(schema = "job", name = "posting_image")
public class PostingImage {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "posting_id", nullable = false)
    private Long postingId;

    @Column(nullable = false)
    private Short seq;

    @Column(nullable = false)
    private String url;

    // rule base 판정 결과, 판정 전이면 null
    private Boolean kept;

    protected PostingImage() {
    }

    public Long getId() {
        return id;
    }

    public Long getPostingId() {
        return postingId;
    }

    public Short getSeq() {
        return seq;
    }

    public String getUrl() {
        return url;
    }

    public Boolean getKept() {
        return kept;
    }
}
