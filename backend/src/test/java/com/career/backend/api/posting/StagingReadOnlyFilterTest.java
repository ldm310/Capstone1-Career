package com.career.backend.api.posting;

import com.career.backend.api.common.StagingReadOnlyFilter;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.assertj.core.api.Assertions.assertThat;

class StagingReadOnlyFilterTest {
    @Test void rejectsWritesBeforeTheControllerCanTouchRds() throws Exception {
        for (String method : new String[]{"POST", "PUT", "PATCH", "DELETE"}) {
            var chain = new MockFilterChain();
            var response = new MockHttpServletResponse();
            new StagingReadOnlyFilter().doFilter(new MockHttpServletRequest(method, "/api/users"), response, chain);
            assertThat(response.getStatus()).isEqualTo(405);
            assertThat(response.getHeader("Allow")).isEqualTo("GET, HEAD, OPTIONS");
            assertThat(chain.getRequest()).isNull();
        }
    }

    @Test void allowsReadRequestsThrough() throws Exception {
        for (String method : new String[]{"GET", "HEAD", "OPTIONS"}) {
            var chain = new MockFilterChain();
            var request = new MockHttpServletRequest(method, "/api/postings");
            new StagingReadOnlyFilter().doFilter(request, new MockHttpServletResponse(), chain);
            assertThat(chain.getRequest()).isSameAs(request);
        }
    }
}
