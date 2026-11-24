package com.career.backend.domain.job;

import org.springframework.data.repository.Repository;
import java.util.List;

public interface TechRepository extends Repository<Tech, Long> {
    List<Tech> findAll();
}
