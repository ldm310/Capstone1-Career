package com.career.backend.api.profile;

import com.career.backend.TestFixtures;
import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;

import java.nio.charset.StandardCharsets;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@Transactional
class ProfileControllerTest {

    private static final byte[] PDF_BYTES =
            "%PDF-1.4\n%test\n".getBytes(StandardCharsets.US_ASCII);

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
    void 사용자를_만들고_같은_이메일은_409를_반환한다() throws Exception {
        long userId = createUser("dup@test.com");

        mockMvc.perform(get("/api/users/" + userId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("dup@test.com"));

        mockMvc.perform(post("/api/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"dup@test.com\",\"name\":\"다른사람\"}"))
                .andExpect(status().isConflict());
    }

    @Test
    void 잘못된_이메일은_400을_반환한다() throws Exception {
        mockMvc.perform(post("/api/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"not-email\",\"name\":\"나\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void GitHub_링크로_프로젝트를_등록한다() throws Exception {
        long userId = createUser("github@test.com");

        mockMvc.perform(multipart("/api/users/" + userId + "/projects")
                        .param("projectName", "커리어")
                        .param("repositoryUrl", "https://github.com/owner/career/"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.repositoryUrl").value("https://github.com/owner/career"))
                .andExpect(jsonPath("$.hasDescriptionFile").value(false));

        mockMvc.perform(get("/api/users/" + userId + "/projects"))
                .andExpect(jsonPath("$", hasSize(1)));
    }

    @Test
    void PDF로_프로젝트를_등록하고_내려받는다() throws Exception {
        long userId = createUser("pdf@test.com");

        String body = mockMvc.perform(multipart("/api/users/" + userId + "/projects")
                        .file(new MockMultipartFile("file", "intro.pdf", "application/pdf", PDF_BYTES))
                        .param("projectName", "PDF 프로젝트"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.hasDescriptionFile").value(true))
                .andExpect(jsonPath("$.descriptionFileType").value("PDF"))
                .andReturn().getResponse().getContentAsString();

        long projectId = ((Number) JsonPath.read(body, "$.projectId")).longValue();

        mockMvc.perform(get("/api/projects/" + projectId + "/description-file"))
                .andExpect(status().isOk())
                .andExpect(content().contentType(MediaType.APPLICATION_PDF))
                .andExpect(content().bytes(PDF_BYTES));
    }

    @Test
    void 링크도_PDF도_없거나_형식이_틀리면_400을_반환한다() throws Exception {
        long userId = createUser("bad@test.com");

        mockMvc.perform(multipart("/api/users/" + userId + "/projects")
                        .param("projectName", "빈 프로젝트"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(multipart("/api/users/" + userId + "/projects")
                        .param("projectName", "링크 틀림")
                        .param("repositoryUrl", "https://gitlab.com/owner/repo"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(multipart("/api/users/" + userId + "/projects")
                        .file(new MockMultipartFile("file", "fake.pdf", "application/pdf", "hello".getBytes()))
                        .param("projectName", "가짜 PDF"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("PDF 파일만 올릴 수 있습니다."));
    }

    @Test
    void 평가_결과를_저장하고_다시_저장하면_덮어쓴다() throws Exception {
        long userId = createUser("eval@test.com");
        long projectId = createProject(userId, "A");

        mockMvc.perform(put("/api/projects/" + projectId + "/evaluations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"evaluations":[
                                  {"capabilityId":1,"confirmedScore":50},
                                  {"capabilityId":2,"confirmedScore":90}
                                ]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.evaluations", hasSize(2)));

        mockMvc.perform(put("/api/projects/" + projectId + "/evaluations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"evaluations\":[{\"capabilityId\":1,\"confirmedScore\":65}]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.evaluations", hasSize(2)))
                .andExpect(jsonPath("$.evaluations[?(@.capabilityId==1)].confirmedScore").value(65))
                .andExpect(jsonPath("$.evaluations[?(@.capabilityId==1)].level").value("LV2"))
                .andExpect(jsonPath("$.evaluations[?(@.capabilityId==2)].level").value("LV3"));
    }

    @Test
    void 평가_점수가_범위를_벗어나거나_사전에_없는_능력이면_실패한다() throws Exception {
        long projectId = createProject(createUser("range@test.com"), "A");

        mockMvc.perform(put("/api/projects/" + projectId + "/evaluations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"evaluations\":[{\"capabilityId\":1,\"confirmedScore\":101}]}"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(put("/api/projects/" + projectId + "/evaluations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"evaluations\":[{\"capabilityId\":1,\"confirmedScore\":10},{\"capabilityId\":1,\"confirmedScore\":20}]}"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(put("/api/projects/" + projectId + "/evaluations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"evaluations\":[{\"capabilityId\":999,\"confirmedScore\":10}]}"))
                .andExpect(status().isNotFound());
    }

    @Test
    void 내_역량은_능력별_최고_점수와_LV로_모인다() throws Exception {
        long userId = createUser("cap@test.com");
        long first = createProject(userId, "첫 프로젝트");
        long second = createProject(userId, "두번째 프로젝트");

        saveScore(first, 1, 20);
        saveScore(second, 1, 88);
        saveScore(second, 2, 35);

        mockMvc.perform(get("/api/users/" + userId + "/capabilities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].capabilityName").value("관계형 DB"))
                .andExpect(jsonPath("$[0].bestScore").value(88))
                .andExpect(jsonPath("$[0].level").value("LV3"))
                .andExpect(jsonPath("$[0].projects", hasSize(2)))
                .andExpect(jsonPath("$[0].projects[0].projectName").value("두번째 프로젝트"))
                .andExpect(jsonPath("$[1].level").value("LV1"));
    }

    @Test
    void 능력_사전은_사용_중인_것만_반환한다() throws Exception {
        mockMvc.perform(get("/api/capabilities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)));
    }

    private long createUser(String email) throws Exception {
        String body = mockMvc.perform(post("/api/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + email + "\",\"name\":\"테스터\"}"))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        return ((Number) JsonPath.read(body, "$.userId")).longValue();
    }

    private long createProject(long userId, String name) throws Exception {
        String body = mockMvc.perform(multipart("/api/users/" + userId + "/projects")
                        .param("projectName", name)
                        .param("repositoryUrl", "https://github.com/owner/" + userId))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        return ((Number) JsonPath.read(body, "$.projectId")).longValue();
    }

    private void saveScore(long projectId, long capabilityId, int score) throws Exception {
        mockMvc.perform(put("/api/projects/" + projectId + "/evaluations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"evaluations\":[{\"capabilityId\":" + capabilityId
                                + ",\"confirmedScore\":" + score + "}]}"))
                .andExpect(status().isOk());
    }
}
