package com.career.backend.api.posting;

import com.career.backend.domain.posting.CapabilityComparisonService;
import jakarta.validation.constraints.Positive;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController
@Validated
@RequestMapping("/api/postings")
public class CapabilityComparisonController {
    private final CapabilityComparisonService service;
    public CapabilityComparisonController(CapabilityComparisonService service) { this.service = service; }
    @GetMapping("/{postingId}/capability-comparison")
    public CapabilityComparisonService.Response compare(@PathVariable @Positive Long postingId,
                                                         @RequestParam @Positive Long userId) {
        return service.compare(postingId, userId);
    }
}
