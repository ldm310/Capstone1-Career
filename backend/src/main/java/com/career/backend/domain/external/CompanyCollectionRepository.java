package com.career.backend.domain.external;

import org.springframework.data.repository.Repository;
import java.util.Optional;

public interface CompanyCollectionRepository extends Repository<CompanyCollection, Long> {
    Optional<CompanyCollection> findById(Long companyId);
}
