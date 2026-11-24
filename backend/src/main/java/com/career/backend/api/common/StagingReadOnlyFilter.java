package com.career.backend.api.common;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Set;

/** The staging RDS bridge exposes reads only; regular profiles retain their API behavior. */
@Component
@Profile("staging-readonly")
public class StagingReadOnlyFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        if (!Set.of("GET", "HEAD", "OPTIONS").contains(request.getMethod())) {
            response.setStatus(405);
            response.setHeader("Allow", "GET, HEAD, OPTIONS");
            response.setContentType("application/json");
            response.getWriter().write("{\"status\":405,\"message\":\"Staging RDS connection is read-only\"}");
            return;
        }
        chain.doFilter(request, response);
    }
}
