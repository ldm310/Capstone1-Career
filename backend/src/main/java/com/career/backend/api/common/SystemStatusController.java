package com.career.backend.api.common;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@Tag(name = "서버 운영 상태", description = "배포 시 백엔드 실행 상태를 확인합니다.")
@RestController
public class SystemStatusController {

    @Operation(summary = "백엔드 실행 상태 확인", description = "서버의 HTTP 응답 가능 여부를 확인합니다. DB 연결과 공고 조회 검증은 배포 점검에서 별도로 수행합니다.")
    @GetMapping("/api/system/status")
    public Map<String, String> status() {
        return Map.of("status", "UP", "service", "Career Backend");
    }
}
