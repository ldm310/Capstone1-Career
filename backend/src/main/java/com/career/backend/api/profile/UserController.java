package com.career.backend.api.profile;

import com.career.backend.domain.profile.*;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@Tag(
        name = "사용자 역량",
        description = "사용자, 프로젝트(GitHub 링크·PDF) 등록과 사용자 역량 LV를 조회합니다."
)
@RestController
@RequestMapping("/api/users")
public class UserController {

    private final UserService userService;
    private final ProjectService projectService;
    private final UserCapabilityService userCapabilityService;

    public UserController(
            UserService userService,
            ProjectService projectService,
            UserCapabilityService userCapabilityService
    ) {
        this.userService = userService;
        this.projectService = projectService;
        this.userCapabilityService = userCapabilityService;
    }

    public record CreateUserRequest(
            @NotBlank @Email String email,
            @NotBlank String name
    ) {
    }

    @Operation(summary = "사용자 생성")
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public UserResponse create(@Valid @RequestBody CreateUserRequest request) {
        return userService.create(request.email().trim(), request.name().trim());
    }

    @Operation(summary = "사용자 조회")
    @GetMapping("/{userId}")
    public UserResponse get(@PathVariable Long userId) {
        return userService.get(userId);
    }

    @Operation(
            summary = "프로젝트 등록",
            description = "GitHub 저장소 링크(repositoryUrl)와 프로젝트 설명 PDF(file) 중 하나 이상을 올립니다. "
                    + "등록된 프로젝트는 커밋 기반 LLM 평가 대상이 됩니다."
    )
    @PostMapping(
            path = "/{userId}/projects",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    @ResponseStatus(HttpStatus.CREATED)
    public ProjectResponse registerProject(
            @PathVariable Long userId,
            @Parameter(description = "프로젝트 이름", example = "Career 백엔드")
            @RequestParam String projectName,
            @Parameter(description = "GitHub 저장소 링크", example = "https://github.com/owner/repo")
            @RequestParam(required = false) String repositoryUrl,
            @Parameter(description = "프로젝트 설명 PDF")
            @RequestPart(name = "file", required = false) MultipartFile file
    ) {
        if (projectName.isBlank()) {
            throw new IllegalArgumentException("프로젝트 이름은 비울 수 없습니다.");
        }

        return projectService.register(userId, projectName, repositoryUrl, file);
    }

    @Operation(summary = "내 프로젝트 목록")
    @GetMapping("/{userId}/projects")
    public List<ProjectResponse> getProjects(@PathVariable Long userId) {
        return projectService.getProjects(userId);
    }

    @Operation(
            summary = "내 역량 LV",
            description = "모든 프로젝트의 평가를 능력별로 모아, 가장 높은 점수와 LV를 반환합니다."
    )
    @GetMapping("/{userId}/capabilities")
    public List<UserCapabilityResponse> getCapabilities(@PathVariable Long userId) {
        return userCapabilityService.getCapabilities(userId);
    }
}
