package com.career.backend.api.application;

import com.career.backend.api.common.GlobalExceptionHandler;
import com.career.backend.domain.application.ApplicationEvaluationResult;
import com.career.backend.domain.application.ApplicationSkillEvaluationService;
import com.career.backend.domain.study.StudyBand;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ApplicationEvaluationControllerTest {

    private ApplicationSkillEvaluationService evaluationService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        evaluationService =
                mock(ApplicationSkillEvaluationService.class);

        ApplicationEvaluationController controller =
                new ApplicationEvaluationController(evaluationService);

        mockMvc = MockMvcBuilders
                .standaloneSetup(controller)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    void 지원자의_역량_평가_API가_결과를_반환한다() throws Exception {
        // given
        ApplicationEvaluationResult result =
                new ApplicationEvaluationResult(
                        1L,
                        3,
                        2.33,
                        StudyBand.MIDDLE
                );

        when(evaluationService.evaluate(1L))
                .thenReturn(result);

        // when & then
        mockMvc.perform(
                        post("/api/applications/1/evaluate")
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.applicationId").value(1))
                .andExpect(jsonPath("$.requiredSkillCount").value(3))
                .andExpect(jsonPath("$.averageSkillScore").value(2.33))
                .andExpect(jsonPath("$.studyBand").value("MIDDLE"));
    }

    @Test
    void 존재하지_않는_지원기록은_404를_반환한다() throws Exception {
        // given
        when(evaluationService.evaluate(999L))
                .thenThrow(
                        new IllegalArgumentException(
                                "지원 기록을 찾을 수 없습니다."
                        )
                );

        // when & then
        mockMvc.perform(
                        post("/api/applications/999/evaluate")
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(
                        jsonPath("$.message")
                                .value("지원 기록을 찾을 수 없습니다.")
                );
    }
}