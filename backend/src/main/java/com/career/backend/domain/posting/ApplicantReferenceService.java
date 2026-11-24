package com.career.backend.domain.posting;

import com.career.backend.domain.profile.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.time.*;
import java.util.*;

@Service
public class ApplicantReferenceService {
    public enum ReferenceType { SAME_COMPANY_SIMILAR_ROLE, MARKET_SAME_ROLE, NONE }
    public record CapabilityStats(Long capabilityId, String capabilityName, int holderCount,
                                  double holderRate, double medianLevel, int sampleSize) {}
    public record Attempt(ReferenceType referenceType, int sampleSize, boolean insufficientData) {}
    public record Reference(ReferenceType referenceType, String referenceLabel, int sampleSize,
                            boolean insufficientData, String reason, List<Attempt> attempts,
                            List<CapabilityStats> capabilities) {}
    private final SuccessfulApplicationRepository applications;
    private final UserSkillEvaluationRepository evaluations;
    private final int minimum;
    public ApplicantReferenceService(SuccessfulApplicationRepository applications,
            UserSkillEvaluationRepository evaluations, @Value("${app.comparison.minimum-sample-size:5}") int minimum) {
        if (minimum < 1) throw new IllegalArgumentException("minimum sample size must be positive");
        this.applications = applications; this.evaluations = evaluations; this.minimum = minimum;
    }
    public Reference select(Long companyId, Long postingId, Long userId, ComparisonTarget target) {
        if (target == null) return none("COMPARISON_TARGET_MISSING", List.of());
        LocalDate today = LocalDate.now(ZoneId.of("Asia/Seoul"));
        var eligible = applications.findEligible(target.getRoleGroup(), target.getCareerBand(),
                today.minusYears(3), today, postingId, userId);
        Set<Long> companyUsers = new LinkedHashSet<>(), marketUsers = new LinkedHashSet<>();
        for (var a : eligible) {
            marketUsers.add(a.getUserId());
            if (companyId.equals(a.getCompanyId())) companyUsers.add(a.getUserId());
        }
        List<Attempt> attempts = new ArrayList<>();
        attempts.add(new Attempt(ReferenceType.SAME_COMPANY_SIMILAR_ROLE, companyUsers.size(), companyUsers.size() < minimum));
        if (companyUsers.size() >= minimum) return aggregate(ReferenceType.SAME_COMPANY_SIMILAR_ROLE,
                "동일 회사 유사 직무 합격자", companyUsers, attempts);
        attempts.add(new Attempt(ReferenceType.MARKET_SAME_ROLE, marketUsers.size(), marketUsers.size() < minimum));
        if (marketUsers.size() >= minimum) return aggregate(ReferenceType.MARKET_SAME_ROLE,
                target.getRoleGroup() + " " + target.getCareerBand() + " 합격자", marketUsers, attempts);
        return none("INSUFFICIENT_SAMPLE", attempts);
    }
    private Reference aggregate(ReferenceType type, String label, Set<Long> users, List<Attempt> attempts) {
        Map<Long, Map<Long, Integer>> levels = new TreeMap<>();
        Map<Long, String> names = new HashMap<>();
        for (var e : evaluations.findAllByUserIds(users)) {
            Long id = e.getCapability().getId();
            names.put(id, e.getCapability().getName());
            levels.computeIfAbsent(id, k -> new HashMap<>()).merge(e.getProject().getUser().getId(),
                    e.getLevel().ordinal(), Math::max);
        }
        List<CapabilityStats> stats = new ArrayList<>();
        levels.forEach((id, byUser) -> {
            // LV0 is insufficient evidence, not a holder. Median is among holders; missing is never LV0.
            var sorted = byUser.values().stream().filter(v -> v > 0).sorted().toList();
            int n = sorted.size();
            if (n > 0) stats.add(new CapabilityStats(id, names.get(id), n, (double)n / users.size(),
                    (sorted.get((n - 1) / 2) + sorted.get(n / 2)) / 2.0, users.size()));
        });
        return new Reference(type, label, users.size(), false, null, List.copyOf(attempts), List.copyOf(stats));
    }
    private Reference none(String reason, List<Attempt> attempts) {
        return new Reference(ReferenceType.NONE, "비교 가능한 합격자 데이터 없음", 0, true, reason,
                List.copyOf(attempts), List.of());
    }
}
