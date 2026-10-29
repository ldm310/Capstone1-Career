package com.career.backend.api.common;

public record ApiErrorResponse(
        int status,
        String message
) {
}