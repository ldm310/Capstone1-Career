package com.career.backend.api.posting;

import com.career.backend.domain.common.NotFoundException;
import com.career.backend.domain.posting.similarity.*;
import com.career.backend.domain.posting.similarity.RecruitUnitFeatures.Category;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import org.springframework.beans.factory.annotation.Autowired;
import com.career.backend.domain.posting.embedding.ShadowEmbeddingService;

@Service
@Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ)
public class ComparisonCandidatesQueryService {
    private final PostingCandidateSelectionService selection;
    private final ComparisonCandidateMetadataRepository metadata;
    private final RoleTaxonomy taxonomy;
    private final ShadowEmbeddingService shadow;
    public ComparisonCandidatesQueryService(PostingCandidateSelectionService selection,
            ComparisonCandidateMetadataRepository metadata,RoleTaxonomy taxonomy) {
        this(selection,metadata,taxonomy,null);
    }
    @Autowired
    public ComparisonCandidatesQueryService(PostingCandidateSelectionService selection,
            ComparisonCandidateMetadataRepository metadata,RoleTaxonomy taxonomy,ShadowEmbeddingService shadow) {
        this.selection=selection;this.metadata=metadata;this.taxonomy=taxonomy;this.shadow=shadow;
    }

    public ComparisonCandidatesResponse get(long postingId,long recruitUnitId) {
        if(postingId<=0||recruitUnitId<=0)throw new IllegalArgumentException("공고와 모집 단위 ID는 양수여야 합니다.");
        if(!metadata.postingExists(postingId))throw new NotFoundException("채용공고를 찾을 수 없습니다.");
        var target=metadata.findUnit(recruitUnitId).orElseThrow(()->new NotFoundException("모집 단위를 찾을 수 없습니다."));
        if(target.postingId()!=postingId)throw new IllegalArgumentException("모집 단위가 요청한 공고에 속하지 않습니다.");
        var result=selection.select(postingId);
        if(result.status()==PostingCandidateSelectionResponse.Status.DATA_ERROR)
            throw new IllegalStateException("현재 추출 결과에 데이터 오류가 있습니다: "+result.reason().name());
        var unit=result.units().stream().filter(u->u.unitId()==recruitUnitId).findFirst().orElse(null);
        var policy=result.policy();var thresholds=policy.thresholds();
        var criteria=new ComparisonCandidatesResponse.AppliedCriteria(policy.maxCompanies(),policy.maxPostingsPerCompany(),
                policy.maxPostings(),policy.jobFamilyExpansionEnabled(),thresholds.requiredCapabilityMinCoverage(),
                thresholds.requiredTechMinIntersection(),thresholds.minimumTotalEvidence(),thresholds.sparseRequiredSupportingEvidence(),
                thresholds.fallbackMinimumTargetFeatures(),thresholds.fallbackMinimumIntersection());
        if(unit==null) {
            String reason;
            if(!target.current())reason="RECRUIT_UNIT_NOT_CURRENT";
            else if(!target.it())reason="NOT_IT_RECRUIT_UNIT";
            else throw new IllegalStateException("현재 모집 단위의 선정 결과가 일치하지 않습니다.");
            return new ComparisonCandidatesResponse(postingId,recruitUnitId,"NOT_COMPARABLE",reason,null,null,null,
                    "UNKNOWN",0,List.of(reason),policy.version(),taxonomy.getVersion(),criteria,List.of());
        }
        // Only candidates for the requested unit are enriched, in one IN query regardless of their number.
        var details=unit.candidates().isEmpty()?Map.<Long,ComparisonCandidateMetadataRepository.CandidateDetails>of():
                metadata.findCandidateDetails(unit.candidates().stream().map(PostingCandidateSelectionResponse.Candidate::unitId).toList());
        var candidates=unit.candidates().stream().map(c->candidate(c,details.get(c.unitId()))).toList();
        // Enrich only AFTER keyword admission, ordering and company/posting limits are final.
        if(shadow!=null&&!candidates.isEmpty()) {
            var semantic=shadow.score(new ShadowEmbeddingService.UnitRef(unit.unitId(),unit.extractionRunId(),unit.role().roleCode()),
                    unit.candidates().stream().map(c->new ShadowEmbeddingService.UnitRef(c.unitId(),c.extractionRunId(),c.role().roleCode())).toList());
            candidates=candidates.stream().map(c->c.withEmbedding(semantic.get(c.recruitUnitId()))).toList();
        }
        Set<String> reasons=new LinkedHashSet<>();unit.exclusionReasons().forEach(r->reasons.add(r.name()));
        if(candidates.isEmpty())unit.exclusions().forEach(ex->ex.exclusionReasons().forEach(r->reasons.add(r.name())));
        var first=candidates.isEmpty()?null:candidates.getFirst();
        return new ComparisonCandidatesResponse(postingId,recruitUnitId,unit.status().name(),unit.reason().name(),
                first==null?null:first.confidence(),unit.featureMode().name(),unit.role().roleCode(),unit.role().evidence().name(),
                first==null?0:first.evidenceCount(),List.copyOf(reasons),policy.version(),unit.role().taxonomyVersion(),criteria,candidates);
    }

    private ComparisonCandidatesResponse.Candidate candidate(PostingCandidateSelectionResponse.Candidate c,
            ComparisonCandidateMetadataRepository.CandidateDetails details) {
        if(details==null||details.postingId()!=c.postingId()||details.companyId()!=c.companyId()||details.recruitUnitId()!=c.unitId())
            throw new IllegalStateException("참고 후보의 공고·모집 단위 정보가 일치하지 않습니다.");
        var required=c.score().category(Category.REQUIRED);var preferred=c.score().category(Category.PREFERRED);var duties=c.score().category(Category.DUTIES);
        return new ComparisonCandidatesResponse.Candidate(c.rank(),c.postingId(),c.companyId(),details.companyName(),details.postingTitle(),
                c.unitId(),details.recruitUnitName(),c.confidence().name(),c.featureMode().name(),c.evidenceCount(),
                c.requiredEvidenceCount(),c.supportingEvidenceCount(),required.capability().coverage(),required.tech().coverage(),
                preferred.capability().coverage(),preferred.tech().coverage(),duties.capability().coverage(),duties.tech().coverage(),
                new ComparisonCandidatesResponse.Intersections(ids(required),ids(preferred),ids(duties)),
                c.evidenceFlags().stream().map(Enum::name).toList());
    }
    private ComparisonCandidatesResponse.IntersectionIds ids(PostingSimilarityScore.CategoryScore score) {
        return new ComparisonCandidatesResponse.IntersectionIds(score.capability().intersectionIds().stream().sorted().toList(),
                score.tech().intersectionIds().stream().sorted().toList());
    }
}
