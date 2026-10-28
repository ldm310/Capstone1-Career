package com.career.backend.domain.job;

import jakarta.persistence.*;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(schema = "job", name = "recruit_unit")
public class RecruitUnit {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "run_id", nullable = false)
    private Long runId;

    @Column(nullable = false)
    private Short seq;

    @Column(nullable = false)
    private String name;

    @Column(name = "is_it", nullable = false)
    private boolean it;

    // 신입/경력/신입·경력/언급없음
    @Column(nullable = false)
    private String career;

    @Column(name = "years_text", nullable = false)
    private String yearsText;

    @Column(name = "min_years")
    private Short minYears;

    @Column(name = "max_years")
    private Short maxYears;

    protected RecruitUnit() {
    }

    public Long getId() {
        return id;
    }

    public Long getRunId() {
        return runId;
    }

    public Short getSeq() {
        return seq;
    }

    public String getName() {
        return name;
    }

    public boolean isIt() {
        return it;
    }

    public String getCareer() {
        return career;
    }

    public String getYearsText() {
        return yearsText;
    }

    public Short getMinYears() {
        return minYears;
    }

    public Short getMaxYears() {
        return maxYears;
    }
}
