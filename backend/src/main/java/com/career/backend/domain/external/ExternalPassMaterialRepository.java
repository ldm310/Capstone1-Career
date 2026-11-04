package com.career.backend.domain.external;

import org.springframework.data.domain.*;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;

public interface ExternalPassMaterialRepository extends Repository<ExternalPassMaterial, Long> {
    // Recheck against the current posting company even if a legacy/direct writer bypassed constraints.
    @Query(value = """
            select link from PostingPassMaterial link join fetch link.material m, Posting p
            where link.postingId = :postingId and p.id = link.postingId
              and m.companyId = p.company.id and m.jobFamily = 'IT_SW'
              and link.relationType <> com.career.backend.domain.external.MaterialRelationType.EXCLUDED
            order by m.collectedAt desc, m.id desc
            """, countQuery = """
            select count(m) from PostingPassMaterial link join link.material m, Posting p
            where link.postingId = :postingId and p.id = link.postingId
              and m.companyId = p.company.id and m.jobFamily = 'IT_SW'
              and link.relationType <> com.career.backend.domain.external.MaterialRelationType.EXCLUDED
            """)
    Page<PostingPassMaterial> findLinked(Long postingId, Pageable pageable);

    @Query("""
            select distinct m from PostingPassMaterial link join link.material m, Posting p
            where link.postingId = :postingId and p.id = link.postingId
              and m.companyId = p.company.id and m.jobFamily = 'IT_SW'
              and link.relationType <> com.career.backend.domain.external.MaterialRelationType.EXCLUDED
            order by m.id
            """)
    java.util.List<ExternalPassMaterial> findAllLinkedForKeywords(Long postingId);
}
