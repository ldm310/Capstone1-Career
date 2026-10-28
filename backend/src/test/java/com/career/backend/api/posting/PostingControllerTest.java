package com.career.backend.api.posting;

import com.career.backend.TestFixtures;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Transactional
class PostingControllerTest {

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private JdbcTemplate jdbc;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
        TestFixtures.insertAnalyzedPosting(jdbc);
    }

    @Test
    void 공고_목록을_검색어와_상태로_거른다() throws Exception {
        mockMvc.perform(get("/api/postings"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(2))
                .andExpect(jsonPath("$.content[0].postingId").value(2));

        mockMvc.perform(get("/api/postings")
                        .param("keyword", "백엔드")
                        .param("status", "진행"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content", hasSize(1)))
                .andExpect(jsonPath("$.content[0].companyName").value("커리어컴퍼니"));

        mockMvc.perform(get("/api/postings").param("keyword", "커리어"))
                .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void 잘못된_상태값은_400을_반환한다() throws Exception {
        mockMvc.perform(get("/api/postings").param("status", "open"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void 공고_상세는_이미지와_추출_결과를_함께_반환한다() throws Exception {
        mockMvc.perform(get("/api/postings/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("백엔드 개발자 채용"))
                .andExpect(jsonPath("$.images", hasSize(2)))
                .andExpect(jsonPath("$.images[0].seq").value(1))
                .andExpect(jsonPath("$.images[0].url").value("https://img.example/1.png"))
                .andExpect(jsonPath("$.analysis.extractionRunId").value(1))
                .andExpect(jsonPath("$.analysis.recruitUnits", hasSize(2)))
                .andExpect(jsonPath("$.analysis.recruitUnits[0].items", hasSize(3)))
                .andExpect(jsonPath("$.analysis.recruitUnits[0].items[0].requirements[0].capabilityName").value("관계형 DB"))
                .andExpect(jsonPath("$.analysis.recruitUnits[0].items[0].requirements[0].techs[0].techName").value("MySQL"));
    }

    @Test
    void 추출되지_않은_공고는_analysis가_null이다() throws Exception {
        mockMvc.perform(get("/api/postings/2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.images", hasSize(0)))
                .andExpect(jsonPath("$.analysis").value(nullValue()));
    }

    @Test
    void 없는_공고는_404를_반환한다() throws Exception {
        mockMvc.perform(get("/api/postings/999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value("채용공고를 찾을 수 없습니다."));
    }

    @Test
    void 공고_요구_역량마다_사용자_LV를_붙인다() throws Exception {
        jdbc.update("insert into profile.app_user (user_id, email, name, created_at, updated_at) values (10, 'me@test.com', '나', current_timestamp, current_timestamp)");
        jdbc.update("insert into profile.project (project_id, user_id, project_name, created_at, updated_at) values (10, 10, 'A', current_timestamp, current_timestamp)");
        jdbc.update("insert into profile.project (project_id, user_id, project_name, created_at, updated_at) values (11, 10, 'B', current_timestamp, current_timestamp)");
        jdbc.update("insert into profile.user_skill_evaluation (project_id, capability_id, confirmed_score, evaluated_at) values (10, 1, 40, current_timestamp)");
        jdbc.update("insert into profile.user_skill_evaluation (project_id, capability_id, confirmed_score, evaluated_at) values (11, 1, 70, current_timestamp)");

        mockMvc.perform(get("/api/postings/1/fit").param("userId", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.analyzed").value(true))
                // IT가 아닌 모집 단위는 빠진다
                .andExpect(jsonPath("$.recruitUnits", hasSize(1)))
                // 필수 두 줄이 같은 능력이라 하나로 묶인다
                .andExpect(jsonPath("$.recruitUnits[0].required", hasSize(1)))
                .andExpect(jsonPath("$.recruitUnits[0].required[0].capabilityName").value("관계형 DB"))
                .andExpect(jsonPath("$.recruitUnits[0].required[0].sourceTexts", hasSize(2)))
                .andExpect(jsonPath("$.recruitUnits[0].required[0].techs[0]").value("MySQL"))
                // 여러 프로젝트 중 가장 높은 점수
                .andExpect(jsonPath("$.recruitUnits[0].required[0].userScore").value(70))
                .andExpect(jsonPath("$.recruitUnits[0].required[0].userLevel").value("LV2"))
                .andExpect(jsonPath("$.recruitUnits[0].preferred[0].capabilityName").value("컨테이너"))
                .andExpect(jsonPath("$.recruitUnits[0].preferred[0].techs[0]").value("도커"))
                .andExpect(jsonPath("$.recruitUnits[0].preferred[0].evaluated").value(false))
                .andExpect(jsonPath("$.recruitUnits[0].preferred[0].userLevel").value(nullValue()));
    }

    @Test
    void 하위_능력만_평가됐으면_상위_요구_능력은_미평가로_본다() throws Exception {
        jdbc.update("insert into job.capability (id, name, group_name, parent_id, is_active) values (5, 'MySQL 운영', '데이터', 1, true)");
        jdbc.update("insert into profile.app_user (user_id, email, name, created_at, updated_at) values (20, 'child@test.com', '나', current_timestamp, current_timestamp)");
        jdbc.update("insert into profile.project (project_id, user_id, project_name, created_at, updated_at) values (20, 20, 'A', current_timestamp, current_timestamp)");
        jdbc.update("insert into profile.user_skill_evaluation (project_id, capability_id, confirmed_score, evaluated_at) values (20, 5, 95, current_timestamp)");

        mockMvc.perform(get("/api/postings/1/fit").param("userId", "20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.recruitUnits[0].required[0].capabilityId").value(1))
                .andExpect(jsonPath("$.recruitUnits[0].required[0].evaluated").value(false))
                .andExpect(jsonPath("$.recruitUnits[0].required[0].userScore").value(nullValue()))
                .andExpect(jsonPath("$.recruitUnits[0].required[0].userLevel").value(nullValue()));
    }

    @Test
    void 없는_사용자로_적합도를_보면_404를_반환한다() throws Exception {
        mockMvc.perform(get("/api/postings/1/fit").param("userId", "999"))
                .andExpect(status().isNotFound());
    }
}
