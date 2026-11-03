package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

import java.time.OffsetDateTime;

@Entity
@Immutable
@Table(schema = "job", name = "extraction_run")
public class ExtractionRun {

    @org.hibernate.annotations.JdbcTypeCode(org.hibernate.type.SqlTypes.JSON)
    @Column(name = "llm_output_raw", columnDefinition = "jsonb")
    private java.util.Map<String, Object> rawOutput;

    public java.util.List<String> getSkipped() {
        if (rawOutput == null || !(rawOutput.get("skipped") instanceof java.util.List<?> values)) {
            return java.util.List.of();
        }
        return values.stream().filter(String.class::isInstance).map(String.class::cast).toList();
    }

    public boolean hasRawOutput() { return rawOutput != null; }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "posting_id", nullable = false)
    private Long postingId;

    @Column(nullable = false)
    private String model;

    @Column(name = "dict_version", nullable = false)
    private String dictVersion;

    // 공고마다 '현재 사용' 실행은 최대 하나
    @Column(name = "is_current", nullable = false)
    private boolean current;

    @Column(name = "run_at", nullable = false)
    private OffsetDateTime runAt;

    protected ExtractionRun() {
    }

    public Long getId() {
        return id;
    }

    public Long getPostingId() {
        return postingId;
    }

    public String getModel() {
        return model;
    }

    public String getDictVersion() {
        return dictVersion;
    }

    public boolean isCurrent() {
        return current;
    }

    public OffsetDateTime getRunAt() {
        return runAt;
    }
}
