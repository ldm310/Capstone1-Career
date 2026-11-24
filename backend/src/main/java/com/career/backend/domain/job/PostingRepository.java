package com.career.backend.domain.job;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface PostingRepository
        extends JpaRepository<Posting, Long>, JpaSpecificationExecutor<Posting> {

    @Override
    @EntityGraph(attributePaths = "company")
    Page<Posting> findAll(Specification<Posting> spec, Pageable pageable);
}
