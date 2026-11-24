package com.career.backend.domain.posting;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import java.time.LocalDate;
import java.util.List;
public interface SuccessfulApplicationRepository extends JpaRepository<SuccessfulApplication, Long> {
    @Query("""
        select a from SuccessfulApplication a
        where a.roleGroup = :roleGroup and a.careerBand = :careerBand
        and a.verified = true and a.stage in (
          com.career.backend.domain.posting.SuccessfulApplication.Stage.DOCUMENT_PASSED,
          com.career.backend.domain.posting.SuccessfulApplication.Stage.INTERVIEW_PASSED,
          com.career.backend.domain.posting.SuccessfulApplication.Stage.FINAL_PASSED)
        and a.acceptedAt >= :since and a.acceptedAt <= :today
        and a.postingId <> :postingId and a.userId <> :userId
        """)
    List<SuccessfulApplication> findEligible(String roleGroup, String careerBand, LocalDate since,
                                           LocalDate today, Long postingId, Long userId);
}
