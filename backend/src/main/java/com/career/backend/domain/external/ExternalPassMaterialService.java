package com.career.backend.domain.external;

import com.career.backend.domain.common.*;
import com.career.backend.domain.job.PostingRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ExternalPassMaterialService {
    private final PostingRepository postings;
    private final CompanyCollectionRepository collections;
    private final ExternalPassMaterialRepository materials;

    public ExternalPassMaterialService(PostingRepository postings, CompanyCollectionRepository collections,
                                       ExternalPassMaterialRepository materials) {
        this.postings = postings; this.collections = collections; this.materials = materials;
    }

    public ExternalPassMaterialResponse get(Long postingId, int page, int size) {
        var posting = postings.findById(postingId)
                .orElseThrow(() -> new NotFoundException("채용공고를 찾을 수 없습니다."));
        var collection = collections.findById(posting.getCompany().getId())
                .map(ExternalPassMaterialResponse.CollectionInfo::from).orElse(null);
        return new ExternalPassMaterialResponse(postingId, posting.getCompany().getId(), collection,
                PageResponse.of(materials.findLinked(postingId, PageRequest.of(page, size)),
                        ExternalPassMaterialResponse.MaterialInfo::from));
    }
}
