package com.career.backend.api.posting;

import com.career.backend.domain.external.ExternalPassKeywordResponse;
import com.career.backend.domain.external.ExternalPassKeywordService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.Positive;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/postings")
public class ExternalPassKeywordController {
    private final ExternalPassKeywordService service;
    public ExternalPassKeywordController(ExternalPassKeywordService service) { this.service = service; }

    @Operation(summary = "동일 회사 외부 합격자료의 기술 키워드와 공고 필수·우대 기술의 교집합",
            description = "저장된 키워드 언급 자료 수이며 역량 보유·수행 수준·합격 원인을 판단하지 않습니다.")
    @GetMapping("/{postingId}/external-pass-keywords")
    public ExternalPassKeywordResponse get(@PathVariable @Positive Long postingId) {
        return service.get(postingId);
    }
}
