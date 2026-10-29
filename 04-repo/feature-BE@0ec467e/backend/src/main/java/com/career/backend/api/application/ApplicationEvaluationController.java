package com.career.backend.api.application;

import com.career.backend.api.common.ApiErrorResponse;
import com.career.backend.domain.application.ApplicationEvaluationResult;
import com.career.backend.domain.application.ApplicationSkillEvaluationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(
        name = "지원자 역량 평가",
        description = "채용공고의 필수 기술을 기준으로 지원자의 역량 수준을 평가합니다."
)
@RestController
@RequestMapping("/api/applications")
public class ApplicationEvaluationController {

    private final ApplicationSkillEvaluationService evaluationService;

    public ApplicationEvaluationController(
            ApplicationSkillEvaluationService evaluationService
    ) {
        this.evaluationService = evaluationService;
    }

    @Operation(
            summary = "지원자 역량 평가",
            description = "채용공고의 필수 기술과 사용자의 보유 기술 수준을 비교하여 평균 점수와 스터디 등급을 계산합니다."
    )
    @ApiResponses({
            @ApiResponse(
                    responseCode = "200",
                    description = "역량 평가 성공",
                    content = @Content(
                            schema = @Schema(
                                    implementation = ApplicationEvaluationResult.class
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "404",
                    description = "지원 기록을 찾을 수 없음",
                    content = @Content(
                            schema = @Schema(
                                    implementation = ApiErrorResponse.class
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "409",
                    description = "채용공고에 등록된 필수 기술이 없음",
                    content = @Content(
                            schema = @Schema(
                                    implementation = ApiErrorResponse.class
                            )
                    )
            )
    })
    @PostMapping("/{applicationId}/evaluate")
    public ResponseEntity<ApplicationEvaluationResult> evaluate(
            @Parameter(
                    description = "평가할 지원 기록 ID",
                    example = "1"
            )
            @PathVariable Long applicationId
    ) {
        ApplicationEvaluationResult result =
                evaluationService.evaluate(applicationId);

        return ResponseEntity.ok(result);
    }
}