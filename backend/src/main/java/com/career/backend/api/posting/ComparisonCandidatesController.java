package com.career.backend.api.posting;

import com.career.backend.api.common.ApiErrorResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.*;
import io.swagger.v3.oas.annotations.responses.*;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Positive;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/postings")
@Tag(name="합격자료 비교 참고 후보",description="다른 기업의 공고를 비교용 참고 후보로 조회합니다.")
public class ComparisonCandidatesController {
    private final ComparisonCandidatesQueryService query;
    public ComparisonCandidatesController(ComparisonCandidatesQueryService query) { this.query=query; }

    @Operation(summary="모집 단위의 합격자료 비교용 참고 후보 조회",
            description="저장·크롤링·수집 작업을 실행하지 않는 읽기 전용 조회입니다. HIGH는 필수 기준을 통과한 참고 후보이며, "
                    +"LOW는 근거가 적거나 우대·업무 기반으로 찾은 참고 후보입니다. 취업 추천, 합격 가능성 또는 정확도가 검증된 유사도를 뜻하지 않습니다. "
                    +"최상위 confidence/evidenceCount는 1위 후보 기준이며 후보가 없으면 null/0입니다. 계산 불가능한 coverage는 null입니다. "
                    +"NO_CANDIDATES/NOT_COMPARABLE은 200입니다. 과거 추출 또는 비IT 모집 단위도 200 NOT_COMPARABLE입니다.")
    @ApiResponses({
        @ApiResponse(responseCode="200",description="선정 상태와 참고 후보",content=@Content(mediaType="application/json",
                schema=@Schema(implementation=ComparisonCandidatesResponse.class),examples={
                    @ExampleObject(name="HIGH 참고 후보",value=ComparisonCandidatesExamples.SELECTED),
                    @ExampleObject(name="LOW 보조 비교",value=ComparisonCandidatesExamples.LOW),
                    @ExampleObject(name="후보 없음",value=ComparisonCandidatesExamples.NO_CANDIDATES),
                    @ExampleObject(name="비교 불가",value=ComparisonCandidatesExamples.NOT_COMPARABLE)})),
        @ApiResponse(responseCode="400",description="양수가 아닌 ID 또는 모집 단위 소속 불일치",content=@Content(schema=@Schema(implementation=ApiErrorResponse.class))),
        @ApiResponse(responseCode="404",description="공고 또는 모집 단위 없음",content=@Content(schema=@Schema(implementation=ApiErrorResponse.class))),
        @ApiResponse(responseCode="409",description="중복 현재 추출 결과(DATA_ERROR) 또는 후보 데이터 불일치",content=@Content(schema=@Schema(implementation=ApiErrorResponse.class)))
    })
    @GetMapping("/{postingId}/recruit-units/{recruitUnitId}/comparison-candidates")
    public ComparisonCandidatesResponse get(@PathVariable @Positive long postingId,@PathVariable @Positive long recruitUnitId) {
        return query.get(postingId,recruitUnitId);
    }
}
