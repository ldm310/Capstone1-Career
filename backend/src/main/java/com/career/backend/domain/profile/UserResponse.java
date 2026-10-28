package com.career.backend.domain.profile;

import java.time.OffsetDateTime;

public record UserResponse(
        Long userId,
        String email,
        String name,
        OffsetDateTime createdAt
) {

    public static UserResponse from(AppUser user) {
        return new UserResponse(
                user.getId(),
                user.getEmail(),
                user.getName(),
                user.getCreatedAt()
        );
    }
}
