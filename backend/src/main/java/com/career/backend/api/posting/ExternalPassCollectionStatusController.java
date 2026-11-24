package com.career.backend.api.posting;

import com.career.backend.api.common.ApiErrorResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.*;
import io.swagger.v3.oas.annotations.media.*;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Positive;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/postings")
@Tag(name="외부 합격자료 수집 상태")
public class ExternalPassCollectionStatusController {
    private final ExternalPassCollectionStatusService service;
    public ExternalPassCollectionStatusController(ExternalPassCollectionStatusService service) { this.service=service; }
    @Operation(summary="모집 단위의 합격자료 수집 상태 조회",description="읽기 전용 상태 조회입니다. 수집 등록·재시도·크롤링을 실행하지 않습니다. "
            +"직접 연결 자료, HIGH, 근거가 부족할 때 LOW 순으로 사용합니다. LOW는 참고 자료이며 추천·적합 판정이 아닙니다. "
            +"NOT_REQUESTED는 배치 등록 전이며 FAILED/INSUFFICIENT는 자동 재시도하지 않습니다.")
    @ApiResponses({@ApiResponse(responseCode="200",description="수집 상태",content=@Content(mediaType="application/json",schema=@Schema(implementation=ExternalPassCollectionStatusResponse.class))),
        @ApiResponse(responseCode="400",description="잘못된 ID 또는 소속 불일치",content=@Content(schema=@Schema(implementation=ApiErrorResponse.class))),
        @ApiResponse(responseCode="404",description="공고 또는 모집 단위 없음",content=@Content(schema=@Schema(implementation=ApiErrorResponse.class))),
        @ApiResponse(responseCode="409",description="선정 데이터 오류·오래된 수집 요청·미적용 스키마",content=@Content(schema=@Schema(implementation=ApiErrorResponse.class)))})
    @GetMapping("/{postingId}/recruit-units/{recruitUnitId}/external-pass-collection-status")
    public ExternalPassCollectionStatusResponse get(@PathVariable @Positive long postingId,@PathVariable @Positive long recruitUnitId) {
        return service.get(postingId,recruitUnitId);
    }
}
