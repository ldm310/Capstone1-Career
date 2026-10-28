package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;

public interface UnitItemRepository extends JpaRepository<UnitItem, Long> {

    List<UnitItem> findByUnitIdInOrderBySeq(Collection<Long> unitIds);
}
