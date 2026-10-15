package com.career.backend.api.study;

import com.career.backend.api.common.ApiErrorResponse;
import com.career.backend.domain.application.StudyMatchCandidate;
import com.career.backend.domain.application.StudyMatchingService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Tag(
        name = "스터디 매칭",
        description = "동일한 채용공고에 지원한 비슷한 수준의 사용자를 조회합니다."
)
@RestController
@RequestMapping("/api/applications")
public class StudyMatchingController {

    private final StudyMatchingService studyMatchingService;

    public StudyMatchingController(
            StudyMatchingService studyMatchingService
    ) {
        this.studyMatchingService = studyMatchingService;
    }

    @Operation(
            summary = "스터디 매칭 후보 조회",
            description = "같은 채용공고에 지원하고 스터디 매칭에 동의한 동일 등급의 사용자를 조회합니다."
    )
    @ApiResponses({
            @ApiResponse(
                    responseCode = "200",
                    description = "스터디 매칭 후보 조회 성공",
                    content = @Content(
                            array = @ArraySchema(
                                    schema = @Schema(
                                            implementation = StudyMatchCandidate.class
                                    )
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
                    description = "스터디 매칭 미동의 또는 역량 평가 미완료",
                    content = @Content(
                            schema = @Schema(
                                    implementation = ApiErrorResponse.class
                            )
                    )
            )
    })
    @GetMapping("/{applicationId}/study-matches")
    public List<StudyMatchCandidate> findStudyMatches(
            @Parameter(
                    description = "현재 사용자의 지원 기록 ID",
                    example = "1"
            )
            @PathVariable Long applicationId
    ) {
        return studyMatchingService.findCandidates(applicationId);
    }
}