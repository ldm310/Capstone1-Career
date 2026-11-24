package com.career.backend.api.capability;

import com.career.backend.domain.job.CapabilityRepository;
import com.career.backend.domain.job.CapabilityResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Tag(
        name = "표준화 사전",
        description = "공고 요건과 사용자 평가가 함께 쓰는 능력(capability) 사전을 조회합니다."
)
@RestController
@RequestMapping("/api/capabilities")
public class CapabilityController {

    private final CapabilityRepository capabilityRepository;

    public CapabilityController(CapabilityRepository capabilityRepository) {
        this.capabilityRepository = capabilityRepository;
    }

    @Operation(
            summary = "능력 목록",
            description = "사용 중인 능력을 묶음·이름 순으로 반환합니다. LLM 평가 결과를 저장할 때 이 ID를 씁니다."
    )
    @GetMapping
    public List<CapabilityResponse> getCapabilities() {
        return capabilityRepository.findByActiveTrueOrderByGroupNameAscNameAsc()
                .stream()
                .map(CapabilityResponse::from)
                .toList();
    }
}
