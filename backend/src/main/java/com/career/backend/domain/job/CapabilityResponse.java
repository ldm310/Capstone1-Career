package com.career.backend.domain.job;

public record CapabilityResponse(
        Long capabilityId,
        String name,
        String groupName,
        Long parentId
) {

    public static CapabilityResponse from(Capability capability) {
        return new CapabilityResponse(
                capability.getId(),
                capability.getName(),
                capability.getGroupName(),
                capability.getParentId()
        );
    }
}
