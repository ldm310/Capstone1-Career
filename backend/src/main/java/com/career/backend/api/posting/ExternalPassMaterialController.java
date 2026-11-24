package com.career.backend.api.posting;

import com.career.backend.domain.external.*;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/postings")
public class ExternalPassMaterialController {
    private final ExternalPassMaterialService service;
    public ExternalPassMaterialController(ExternalPassMaterialService service) { this.service = service; }

    @Operation(summary = "공고에 연결된 동일 회사 IT·SW 외부 합격자료 조회")
    @GetMapping("/{postingId}/external-pass-materials")
    public ExternalPassMaterialResponse get(@PathVariable @Positive Long postingId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return service.get(postingId, page, size);
    }
}
