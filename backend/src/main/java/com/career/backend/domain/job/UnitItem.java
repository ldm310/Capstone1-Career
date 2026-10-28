package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(schema = "job", name = "unit_item")
public class UnitItem {

    public static final String REQUIRED = "필수";
    public static final String PREFERRED = "우대";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "unit_id", nullable = false)
    private Long unitId;

    // 필수/우대/업무/기타
    @Column(nullable = false)
    private String category;

    @Column(nullable = false)
    private Short seq;

    @Column(nullable = false)
    private String text;

    @Column(nullable = false)
    private String quote;

    protected UnitItem() {
    }

    public Long getId() {
        return id;
    }

    public Long getUnitId() {
        return unitId;
    }

    public String getCategory() {
        return category;
    }

    public Short getSeq() {
        return seq;
    }

    public String getText() {
        return text;
    }

    public String getQuote() {
        return quote;
    }
}
