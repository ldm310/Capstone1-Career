package com.career.backend.api.common;

import com.career.backend.domain.common.NotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(NotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleNotFound(
            NotFoundException exception
    ) {
        return error(HttpStatus.NOT_FOUND, exception.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiErrorResponse> handleIllegalArgument(
            IllegalArgumentException exception
    ) {
        return error(HttpStatus.BAD_REQUEST, exception.getMessage());
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ApiErrorResponse> handleIllegalState(
            IllegalStateException exception
    ) {
        return error(HttpStatus.CONFLICT, exception.getMessage());
    }

    @ExceptionHandler({
            MethodArgumentNotValidException.class,
            HandlerMethodValidationException.class
    })
    public ResponseEntity<ApiErrorResponse> handleValidation(Exception exception) {
        return error(HttpStatus.BAD_REQUEST, "요청 값이 올바르지 않습니다.");
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiErrorResponse> handleMaxUploadSize(
            MaxUploadSizeExceededException exception
    ) {
        return error(HttpStatus.CONTENT_TOO_LARGE, "파일이 너무 큽니다.");
    }

    private static ResponseEntity<ApiErrorResponse> error(
            HttpStatus status,
            String message
    ) {
        return ResponseEntity
                .status(status)
                .body(new ApiErrorResponse(status.value(), message));
    }
}
