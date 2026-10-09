package com.career.backend.api.application;

import com.career.backend.domain.application.ApplicationEvaluationResult;
import com.career.backend.domain.application.ApplicationSkillEvaluationService;
import com.career.backend.domain.study.StudyBand;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ApplicationEvaluationControllerTest {

    @Test
    void 지원자의_역량_평가_API가_결과를_반환한다() throws Exception {
        // given
        ApplicationSkillEvaluationService evaluationService =
                mock(ApplicationSkillEvaluationService.class);

        ApplicationEvaluationController controller =
                new ApplicationEvaluationController(evaluationService);

        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(controller)
                .build();

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
}