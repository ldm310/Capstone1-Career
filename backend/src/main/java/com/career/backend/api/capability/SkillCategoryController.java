package com.career.backend.api.capability;

import com.career.backend.domain.posting.PostingQueryService;
import com.career.backend.domain.posting.SkillCategoryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "문장 기술 카테고리", description = "저장된 문장 분류 조회. 기존 역량 ID·LV와 별도이며 실시간 임베딩하지 않습니다.")
@RestController
public class SkillCategoryController {
    private final SkillCategoryService categories;
    private final PostingQueryService postings;

    public SkillCategoryController(SkillCategoryService categories, PostingQueryService postings) {
        this.categories = categories;
        this.postings = postings;
    }

    @Operation(summary = "기술 카테고리·기타 관련 묶음", description = "기술 10개, 보조 태그, 기타 검토 묶음 및 저장 코퍼스 집계. 실시간 DB 공고 건수가 아니며 중복 배정됩니다. 자격증은 별도 참고 묶음입니다.")
    @GetMapping("/api/skill-categories")
    public SkillCategoryService.Catalog catalog() { return categories.catalog(); }

    @Operation(summary = "공고 필수·우대 문장의 저장된 기술 분류", description = "현재 추출 원문을 NFC·공백 정규화 후 저장된 분류와 일치시킵니다. 새 문장은 UNCLASSIFIED, 제외는 EXCLUDED, 기타는 CLASSIFIED+OTHER입니다. 업무·기타 항목은 NOT_APPLICABLE이며 LV를 계산하지 않습니다.")
    @GetMapping("/api/postings/{postingId}/skill-categories")
    public SkillCategoryService.PostingCategories forPosting(@PathVariable Long postingId) {
        return categories.forPosting(postings.getDetail(postingId));
    }
}
