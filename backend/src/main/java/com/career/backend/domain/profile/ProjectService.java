package com.career.backend.domain.profile;

import com.career.backend.domain.common.NotFoundException;
import com.career.backend.domain.job.Capability;
import com.career.backend.domain.job.CapabilityRepository;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Service
@Transactional(readOnly = true)
public class ProjectService {

    private static final Pattern GITHUB_REPOSITORY = Pattern.compile(
            "^https://github\\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+/?$"
    );

    private final UserService userService;
    private final ProjectRepository projectRepository;
    private final UserSkillEvaluationRepository evaluationRepository;
    private final CapabilityRepository capabilityRepository;
    private final ProjectFileStorage fileStorage;

    public ProjectService(
            UserService userService,
            ProjectRepository projectRepository,
            UserSkillEvaluationRepository evaluationRepository,
            CapabilityRepository capabilityRepository,
            ProjectFileStorage fileStorage
    ) {
        this.userService = userService;
        this.projectRepository = projectRepository;
        this.evaluationRepository = evaluationRepository;
        this.capabilityRepository = capabilityRepository;
        this.fileStorage = fileStorage;
    }

    // PDF와 GitHub 링크 중 하나 이상은 있어야 역량을 평가할 수 있다.
    @Transactional
    public ProjectResponse register(
            Long userId,
            String projectName,
            String repositoryUrl,
            MultipartFile descriptionFile
    ) {
        AppUser user = userService.find(userId);

        String normalizedUrl = normalizeRepositoryUrl(repositoryUrl);
        boolean hasFile = descriptionFile != null && !descriptionFile.isEmpty();

        if (normalizedUrl == null && !hasFile) {
            throw new IllegalArgumentException(
                    "GitHub 저장소 링크나 PDF 파일 중 하나는 필요합니다."
            );
        }

        String filePath = hasFile ? fileStorage.storePdf(descriptionFile) : null;

        Project project = projectRepository.save(new Project(
                user,
                projectName.trim(),
                normalizedUrl,
                filePath,
                hasFile ? ProjectFileStorage.PDF : null
        ));

        return ProjectResponse.from(project);
    }

    public List<ProjectResponse> getProjects(Long userId) {
        userService.find(userId);

        return projectRepository.findByUser_IdOrderByIdDesc(userId).stream()
                .map(ProjectResponse::from)
                .toList();
    }

    public ProjectDetailResponse getProject(Long projectId) {
        return toDetail(find(projectId));
    }

    public Resource loadDescriptionFile(Long projectId) {
        Project project = find(projectId);

        if (project.getDescriptionFilePath() == null) {
            throw new NotFoundException("등록된 설명 파일이 없습니다.");
        }

        return fileStorage.load(project.getDescriptionFilePath());
    }

    // LLM 평가 결과를 받아 프로젝트별 능력 점수를 저장한다. 이미 있으면 덮어쓴다.
    @Transactional
    public ProjectDetailResponse saveEvaluations(
            Long projectId,
            List<EvaluationScore> scores
    ) {
        Project project = find(projectId);

        Set<Long> capabilityIds = new HashSet<>();
        for (EvaluationScore score : scores) {
            if (!capabilityIds.add(score.capabilityId())) {
                throw new IllegalArgumentException(
                        "같은 능력이 두 번 들어 있습니다: " + score.capabilityId()
                );
            }
        }

        Map<Long, Capability> capabilities =
                capabilityRepository.findAllById(capabilityIds).stream()
                        .collect(Collectors.toMap(
                                Capability::getId,
                                Function.identity()
                        ));

        if (capabilities.size() != capabilityIds.size()) {
            capabilityIds.removeAll(capabilities.keySet());
            throw new NotFoundException(
                    "표준화 사전에 없는 능력입니다: " + capabilityIds
            );
        }

        Map<Long, UserSkillEvaluation> existing =
                evaluationRepository.findWithCapabilityByProjectId(projectId)
                        .stream()
                        .collect(Collectors.toMap(
                                evaluation -> evaluation.getCapability().getId(),
                                Function.identity()
                        ));

        for (EvaluationScore score : scores) {
            UserSkillEvaluation evaluation = existing.get(score.capabilityId());

            if (evaluation == null) {
                evaluationRepository.save(new UserSkillEvaluation(
                        project,
                        capabilities.get(score.capabilityId()),
                        score.confirmedScore()
                ));
            } else {
                evaluation.updateScore(score.confirmedScore());
            }
        }

        evaluationRepository.flush();

        return toDetail(project);
    }

    private Project find(Long projectId) {
        return projectRepository.findById(projectId)
                .orElseThrow(() ->
                        new NotFoundException("프로젝트를 찾을 수 없습니다.")
                );
    }

    private ProjectDetailResponse toDetail(Project project) {
        return new ProjectDetailResponse(
                ProjectResponse.from(project),
                evaluationRepository.findWithCapabilityByProjectId(project.getId())
                        .stream()
                        .map(ProjectDetailResponse.EvaluationResponse::from)
                        .toList()
        );
    }

    private static String normalizeRepositoryUrl(String repositoryUrl) {
        if (repositoryUrl == null || repositoryUrl.isBlank()) {
            return null;
        }

        String url = repositoryUrl.trim();

        if (!GITHUB_REPOSITORY.matcher(url).matches()) {
            throw new IllegalArgumentException(
                    "GitHub 저장소 링크 형식이 아닙니다. 예: https://github.com/owner/repo"
            );
        }

        return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
    }
}
