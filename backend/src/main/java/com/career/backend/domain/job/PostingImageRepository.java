package com.career.backend.domain.job;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface PostingImageRepository
        extends JpaRepository<PostingImage, Long> {

    List<PostingImage> findByPostingIdOrderBySeq(Long postingId);
}
