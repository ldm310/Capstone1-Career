package com.career.backend.api.profile;

import com.career.backend.domain.profile.EvaluationScore;
import com.career.backend.domain.profile.ProjectDetailResponse;
import com.career.backend.domain.profile.ProjectService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Tag(
        name = "프로젝트 역량 평가",
        description = "프로젝트별 역량 평가 결과를 조회하거나, LLM 평가기가 결과를 저장합니다."
)
@RestController
@RequestMapping("/api/projects")
public class ProjectController {

    private final ProjectService projectService;

    public ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    public record SaveEvaluationsRequest(
            @NotEmpty List<@Valid EvaluationItem> evaluations
    ) {
    }

    public record EvaluationItem(
            @NotNull Long capabilityId,
            @NotNull @Min(0) @Max(100) Integer confirmedScore
    ) {
    }

    @Operation(
            summary = "프로젝트 상세와 역량 평가",
            description = "프로젝트 정보와 능력별 확정 점수·LV를 반환합니다."
    )
    @GetMapping("/{projectId}")
    public ProjectDetailResponse get(@PathVariable Long projectId) {
        return projectService.getProject(projectId);
    }

    @Operation(
            summary = "역량 평가 결과 저장 (LLM 평가기용)",
            description = "커밋 기반 LLM 평가 결과를 능력 ID와 0~100 점수로 저장합니다. "
                    + "같은 프로젝트·능력에 이미 점수가 있으면 덮어씁니다."
    )
    @PutMapping("/{projectId}/evaluations")
    public ProjectDetailResponse saveEvaluations(
            @PathVariable Long projectId,
            @Valid @RequestBody SaveEvaluationsRequest request
    ) {
        List<EvaluationScore> scores = request.evaluations().stream()
                .map(item -> new EvaluationScore(
                        item.capabilityId(),
                        item.confirmedScore()
                ))
                .toList();

        return projectService.saveEvaluations(projectId, scores);
    }

    @Operation(
            summary = "프로젝트 설명 PDF 내려받기",
            description = "LLM 평가기가 평가 자료로 쓸 수 있도록 등록된 PDF를 반환합니다."
    )
    @GetMapping(
            path = "/{projectId}/description-file",
            produces = MediaType.APPLICATION_PDF_VALUE
    )
    public ResponseEntity<Resource> getDescriptionFile(@PathVariable Long projectId) {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .body(projectService.loadDescriptionFile(projectId));
    }
}
