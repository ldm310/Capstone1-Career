package com.career.backend.domain.posting.similarity;

import com.career.backend.domain.common.NotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import static com.career.backend.domain.posting.similarity.PostingCandidateSelectionResponse.*;
import com.career.backend.domain.posting.similarity.RecruitUnitRoleResolver.RoleMatch;

@Service
@Transactional(readOnly=true)
public class PostingCandidateSelectionService {
    private final RecruitUnitFeatureRepository repository;
    private final RecruitUnitRoleResolver resolver;
    private final PostingSimilarityScorer scorer;
    private final PostingSimilarityProperties properties;
    private final PostingCandidateEligibility eligibility;

    public PostingCandidateSelectionService(RecruitUnitFeatureRepository repository, RecruitUnitRoleResolver resolver,
            PostingSimilarityScorer scorer, PostingSimilarityProperties properties) {
        this.repository=repository; this.resolver=resolver; this.scorer=scorer; this.properties=properties;
        this.eligibility=new PostingCandidateEligibility(properties);
    }

    public PostingCandidateSelectionResponse select(long postingId) {
        if (postingId<=0) throw new IllegalArgumentException("A positive posting ID is required");
        var snapshot=repository.load(postingId);
        if (snapshot.targetCompanyId()==null) throw new NotFoundException("채용공고를 찾을 수 없습니다.");
        var issues=snapshot.currentRunCounts().entrySet().stream().filter(e -> e.getValue()>1)
                .sorted(Map.Entry.comparingByKey())
                .map(e -> new DataIssue(e.getKey(),e.getValue(),Reason.DUPLICATE_CURRENT_EXTRACTION)).toList();
        if (!issues.isEmpty()) return response(snapshot,Status.DATA_ERROR,Reason.DUPLICATE_CURRENT_EXTRACTION,issues,List.of());
        if (snapshot.currentRunCounts().getOrDefault(postingId,0)==0)
            return response(snapshot,Status.NOT_COMPARABLE,Reason.NO_CURRENT_EXTRACTION,List.of(),List.of());
        var targets=snapshot.units().stream().filter(u -> u.postingId()==postingId)
                .sorted(Comparator.comparingLong(RecruitUnitFeatures::unitId)).toList();
        if (targets.isEmpty()) return response(snapshot,Status.NOT_COMPARABLE,Reason.NO_IT_RECRUIT_UNIT,List.of(),List.of());
        var candidates=snapshot.units().stream().filter(u -> u.companyId()!=snapshot.targetCompanyId()).toList();
        Map<Long,RoleMatch> roles=new HashMap<>();
        snapshot.units().forEach(u -> roles.put(u.unitId(),resolver.resolve(u)));
        var results=targets.stream().map(t -> selectUnit(t,roles,candidates)).toList();
        Status status=results.stream().anyMatch(u -> u.status()==Status.SELECTED) ? Status.SELECTED
                : results.stream().anyMatch(u -> u.status()==Status.NO_CANDIDATES) ? Status.NO_CANDIDATES : Status.NOT_COMPARABLE;
        return response(snapshot,status,Reason.NONE,List.of(),results);
    }

    private UnitSelection selectUnit(RecruitUnitFeatures target, Map<Long,RoleMatch> roles,
                                     List<RecruitUnitFeatures> candidates) {
        RoleMatch role=roles.get(target.unitId());
        if (!role.resolved()) return unavailable(target,role,role.status()==RecruitUnitRoleResolver.Status.AMBIGUOUS
                ? Reason.AMBIGUOUS_ROLE : Reason.UNKNOWN_ROLE);
        if (!target.hasRequiredFeatures() && eligibility.supportingFeatureCount(target)<properties.getFallbackMinimumTargetFeatures())
            return unavailable(target,role,Reason.REQUIRED_FEATURES_MISSING);
        List<Exclusion> exclusions=new ArrayList<>();
        var exact=rank(target,role,roles,candidates,Stage.EXACT_ROLE,exclusions);
        var selected=limit(exact);
        // No role-pair allowlist exists. Family expansion remains disabled, including empty exact results.
        List<Candidate> ranked=new ArrayList<>();
        for (int i=0;i<selected.size();i++) {
            var c=selected.get(i);
            ranked.add(c.withRank(i+1));
        }
        if (ranked.isEmpty() && !target.hasRequiredFeatures())
            return new UnitSelection(target.unitId(),target.runId(),role,Status.NOT_COMPARABLE,Reason.REQUIRED_FEATURES_MISSING,
                    Stage.NONE,false,List.of(),exclusions,FeatureMode.FALLBACK_FEATURES,List.of(Reason.REQUIRED_FEATURES_MISSING));
        return new UnitSelection(target.unitId(),target.runId(),role,
                ranked.isEmpty() ? Status.NO_CANDIDATES : Status.SELECTED,
                ranked.isEmpty() ? Reason.NO_ELIGIBLE_CANDIDATE : Reason.NONE,
                ranked.isEmpty() ? Stage.NONE : Stage.EXACT_ROLE,false,ranked,exclusions,eligibility.mode(target),
                ranked.isEmpty() ? List.of(Reason.NO_ELIGIBLE_CANDIDATE) : List.of());
    }

    private List<Candidate> rank(RecruitUnitFeatures target, RoleMatch role, Map<Long,RoleMatch> roles,
            List<RecruitUnitFeatures> units, Stage stage, List<Exclusion> exclusions) {
        List<Candidate> ranked=new ArrayList<>();
        for (var unit : units) {
            RoleMatch candidateRole=roles.get(unit.unitId());
            if (!candidateRole.resolved()) {
                Reason reason=candidateRole.status()==RecruitUnitRoleResolver.Status.AMBIGUOUS ? Reason.AMBIGUOUS_ROLE : Reason.UNKNOWN_ROLE;
                exclusions.add(new Exclusion(unit.postingId(),unit.unitId(),reason,candidateRole,List.of(reason)));
                continue;
            }
            boolean sameRole=role.roleCode().equals(candidateRole.roleCode());
            if (!sameRole) continue;
            var score=scorer.score(target,unit);
            var admission=eligibility.evaluate(target,score);
            if (!admission.allowed()) {
                exclusions.add(new Exclusion(unit.postingId(),unit.unitId(),admission.exclusionReasons().getFirst(),candidateRole,admission.exclusionReasons()));
                continue;
            }
            ranked.add(new Candidate(0,unit.postingId(),unit.companyId(),unit.unitId(),unit.runId(),Stage.EXACT_ROLE,candidateRole,score,
                    admission.confidence(),admission.featureMode(),admission.evidenceCount(),admission.requiredEvidenceCount(),
                    admission.supportingEvidenceCount(),admission.flags(),List.of()));
        }
        ranked.sort((a,b) -> {
            int result=PostingSimilarityScore.compareBestFirst(a.score(),b.score());
            if (result!=0) return result;
            result=Long.compare(a.postingId(),b.postingId());
            return result!=0 ? result : Long.compare(a.unitId(),b.unitId());
        });
        // Per target unit, keep only the best unit of each candidate posting.
        Map<Long,Candidate> representatives=new LinkedHashMap<>();
        ranked.forEach(c -> representatives.putIfAbsent(c.postingId(),c));
        return List.copyOf(representatives.values());
    }

    private List<Candidate> limit(List<Candidate> candidates) {
        Map<Long,Integer> companyCounts=new HashMap<>();
        List<Candidate> selected=new ArrayList<>();
        for (var candidate : candidates) {
            long companyId=candidate.companyId();
            if (!companyCounts.containsKey(companyId) && companyCounts.size()>=properties.getMaxCompanies()) continue;
            if (companyCounts.getOrDefault(companyId,0)>=properties.getMaxPostingsPerCompany()) continue;
            selected.add(candidate); companyCounts.merge(companyId,1,Integer::sum);
            if (selected.size()>=properties.getMaxPostings()) break;
        }
        return selected;
    }

    private UnitSelection unavailable(RecruitUnitFeatures target, RoleMatch role, Reason reason) {
        return new UnitSelection(target.unitId(),target.runId(),role,Status.NOT_COMPARABLE,reason,Stage.NONE,false,List.of(),List.of(),eligibility.mode(target),List.of(reason));
    }
    private PostingCandidateSelectionResponse response(RecruitUnitFeatureRepository.Snapshot snapshot, Status status,
            Reason reason, List<DataIssue> issues, List<UnitSelection> units) {
        return new PostingCandidateSelectionResponse(snapshot.targetPostingId(),snapshot.targetCompanyId(),status,reason,
                "NOT_AVAILABLE",new Policy(properties.getPolicyVersion(),properties.getMaxCompanies(),
                properties.getMaxPostingsPerCompany(),properties.getMaxPostings(),false,
                new Thresholds(properties.getRequiredCapabilityMinCoverage(),properties.getRequiredTechMinIntersection(),
                        properties.getMinimumTotalEvidence(),properties.getSparseRequiredSupportingEvidence(),
                        properties.getFallbackMinimumTargetFeatures(),properties.getFallbackMinimumIntersection())),issues,units);
    }
}
