package com.career.backend.api.posting;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
class SystemStatusControllerTest {
    @Autowired WebApplicationContext context;
    MockMvc mvc;

    @BeforeEach void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test void deploymentStatusIsAvailableAtTheNewRouteOnly() throws Exception {
        mvc.perform(get("/api/system/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.service").value("Career Backend"));
        mvc.perform(get("/api/health")).andExpect(status().isNotFound());
    }

    @Test void swaggerDocumentsTheOperationalRoute() throws Exception {
        mvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/system/status'].get.tags[0]").value("서버 운영 상태"))
                .andExpect(jsonPath("$.paths['/api/health']").doesNotExist());
    }
}
