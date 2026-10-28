package com.career.backend.api.posting;

import com.career.backend.domain.common.PageResponse;
import com.career.backend.domain.posting.PostingDetailResponse;
import com.career.backend.domain.posting.PostingFitResponse;
import com.career.backend.domain.posting.PostingQueryService;
import com.career.backend.domain.posting.PostingSummaryResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@Tag(
        name = "채용공고 분석",
        description = "수집된 채용공고와 LLM 추출 결과(모집 단위·필수/우대 요건·기술)를 조회합니다."
)
@Validated
@RestController
@RequestMapping("/api/postings")
public class PostingController {

    private final PostingQueryService postingQueryService;

    public PostingController(PostingQueryService postingQueryService) {
        this.postingQueryService = postingQueryService;
    }

    @Operation(
            summary = "채용공고 목록",
            description = "제목·회사명 검색과 상태(진행/마감) 필터로 공고를 최신순으로 조회합니다."
    )
    @GetMapping
    public PageResponse<PostingSummaryResponse> search(
            @Parameter(description = "제목 또는 회사명 검색어", example = "백엔드")
            @RequestParam(required = false) String keyword,
            @Parameter(description = "공고 상태 (진행/마감)", example = "진행")
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size
    ) {
        return postingQueryService.search(keyword, status, page, size);
    }

    @Operation(
            summary = "채용공고 상세 분석",
            description = "공고 기본 정보, 공고 이미지, 현재 추출 결과(모집 단위 → 항목 → 요건 → 기술)를 함께 반환합니다. "
                    + "아직 추출되지 않은 공고는 analysis가 null입니다."
    )
    @GetMapping("/{postingId}")
    public PostingDetailResponse getDetail(
            @Parameter(description = "공고 ID", example = "1")
            @PathVariable Long postingId
    ) {
        return postingQueryService.getDetail(postingId);
    }

    @Operation(
            summary = "공고 요구 역량 대비 내 LV",
            description = "모집 단위별 필수/우대 역량마다 사용자의 확정 점수와 LV를 붙여 반환합니다. "
                    + "평가된 적 없는 역량은 evaluated=false, userLevel=null입니다."
    )
    @GetMapping("/{postingId}/fit")
    public PostingFitResponse getFit(
            @Parameter(description = "공고 ID", example = "1")
            @PathVariable Long postingId,
            @Parameter(description = "사용자 ID", example = "1")
            @RequestParam Long userId
    ) {
        return postingQueryService.getFit(postingId, userId);
    }
}
