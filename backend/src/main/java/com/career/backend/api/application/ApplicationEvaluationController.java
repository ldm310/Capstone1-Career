package com.career.backend.api.application;

import com.career.backend.domain.application.ApplicationEvaluationResult;
import com.career.backend.domain.application.ApplicationSkillEvaluationService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/applications")
public class ApplicationEvaluationController {

    private final ApplicationSkillEvaluationService evaluationService;

    public ApplicationEvaluationController(
            ApplicationSkillEvaluationService evaluationService
    ) {
        this.evaluationService = evaluationService;
    }

    @PostMapping("/{applicationId}/evaluate")
    public ResponseEntity<ApplicationEvaluationResult> evaluate(
            @PathVariable Long applicationId
    ) {
        ApplicationEvaluationResult result =
                evaluationService.evaluate(applicationId);

        return ResponseEntity.ok(result);
    }
}