package com.career.backend.domain.profile;

import com.career.backend.domain.common.NotFoundException;
import com.career.backend.domain.job.Capability;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
@Transactional(readOnly = true)
public class UserCapabilityService {

    private final AppUserRepository appUserRepository;
    private final UserSkillEvaluationRepository evaluationRepository;

    public UserCapabilityService(
            AppUserRepository appUserRepository,
            UserSkillEvaluationRepository evaluationRepository
    ) {
        this.appUserRepository = appUserRepository;
        this.evaluationRepository = evaluationRepository;
    }

    // 여러 프로젝트에서 같은 능력이 평가됐으면 가장 높은 점수를 사용자 점수로 본다.
    public Map<Long, Integer> findBestScores(Long userId) {
        return findEvaluations(userId).stream()
                .collect(Collectors.toMap(
                        evaluation -> evaluation.getCapability().getId(),
                        UserSkillEvaluation::getConfirmedScore,
                        Math::max
                ));
    }

    public List<UserCapabilityResponse> getCapabilities(Long userId) {
        Map<Capability, List<UserSkillEvaluation>> byCapability =
                findEvaluations(userId).stream()
                        .collect(Collectors.groupingBy(
                                UserSkillEvaluation::getCapability
                        ));

        return byCapability.entrySet().stream()
                .map(entry -> toResponse(entry.getKey(), entry.getValue()))
                .sorted(Comparator
                        .comparingInt(UserCapabilityResponse::bestScore)
                        .reversed()
                        .thenComparing(UserCapabilityResponse::capabilityName))
                .toList();
    }

    private List<UserSkillEvaluation> findEvaluations(Long userId) {
        if (!appUserRepository.existsById(userId)) {
            throw new NotFoundException("사용자를 찾을 수 없습니다.");
        }

        return evaluationRepository.findAllByUserId(userId);
    }

    private static UserCapabilityResponse toResponse(
            Capability capability,
            List<UserSkillEvaluation> evaluations
    ) {
        List<UserCapabilityResponse.ProjectScoreResponse> projects =
                evaluations.stream()
                        .sorted(Comparator.comparing(
                                UserSkillEvaluation::getConfirmedScore
                        ).reversed())
                        .map(evaluation ->
                                new UserCapabilityResponse.ProjectScoreResponse(
                                        evaluation.getProject().getId(),
                                        evaluation.getProject().getProjectName(),
                                        evaluation.getConfirmedScore(),
                                        evaluation.getLevel(),
                                        evaluation.getEvaluatedAt()
                                ))
                        .toList();

        int bestScore = projects.getFirst().score();

        return new UserCapabilityResponse(
                capability.getId(),
                capability.getName(),
                capability.getGroupName(),
                bestScore,
                SkillLevel.fromScore(bestScore),
                projects
        );
    }
}
