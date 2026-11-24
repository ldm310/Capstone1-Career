package com.career.backend.domain.posting;

import jakarta.persistence.*;
import lombok.Getter;
import java.time.LocalDate;

@Entity
@Getter
@Table(schema = "profile", name = "successful_application")
public class SuccessfulApplication {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) private Long id;
    @Column(nullable = false) private Long userId;
    @Column(nullable = false) private Long companyId;
    @Column(nullable = false) private Long postingId;
    @Column(nullable = false) private String roleGroup;
    @Column(nullable = false) private String careerBand;
    @Enumerated(EnumType.STRING) @Column(nullable = false) private Stage stage;
    @Column(nullable = false) private boolean verified;
    @Column(nullable = false) private LocalDate acceptedAt;
    public enum Stage { APPLIED, DOCUMENT_PASSED, INTERVIEW_PASSED, FINAL_PASSED }
    protected SuccessfulApplication() {}
}
