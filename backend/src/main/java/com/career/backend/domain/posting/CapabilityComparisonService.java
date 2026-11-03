package com.career.backend.domain.posting;

import com.career.backend.domain.common.NotFoundException;
import com.career.backend.domain.job.*;
import com.career.backend.domain.profile.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import static com.career.backend.domain.posting.PostingDetailResponse.*;

@Service
@Transactional(readOnly = true)
public class CapabilityComparisonService {
    public record UnitComparison(PostingResultAdapter.Position posting,
                                 ApplicantReferenceService.Reference reference) {}
    public record Response(Long postingId, Long userId, boolean analyzed, boolean skippedAvailable,
                           List<UserCapabilityResponse> userCapabilities, List<UnitComparison> positions) {}
    private final PostingRepository postings;
    private final ExtractionTreeLoader loader;
    private final PostingResultAdapter adapter;
    private final UserCapabilityService users;
    private final ComparisonTargetRepository targets;
    private final ApplicantReferenceService references;
    public CapabilityComparisonService(PostingRepository postings, ExtractionTreeLoader loader,
            PostingResultAdapter adapter, UserCapabilityService users,
            ComparisonTargetRepository targets, ApplicantReferenceService references) {
        this.postings = postings; this.loader = loader; this.adapter = adapter;
        this.users = users; this.targets = targets; this.references = references;
    }
    public Response compare(Long postingId, Long userId) {
        var posting = postings.findById(postingId).orElseThrow(() -> new NotFoundException("채용공고를 찾을 수 없습니다."));
        var evidence = users.getCapabilities(userId);
        var current = loader.loadCurrent(postingId);
        if (current.isEmpty()) return new Response(postingId, userId, false, false, evidence, List.of());
        var tree = current.get();
        var metadata = targets.findAllById(tree.units().stream().map(RecruitUnit::getId).toList());
        Map<Long, ComparisonTarget> byUnit = new HashMap<>();
        metadata.forEach(t -> byUnit.put(t.getUnitId(), t));
        List<UnitComparison> positions = tree.units().stream().map(unit -> {
            var dto = new RecruitUnitResponse(unit.getId(), unit.getSeq(), unit.getName(), unit.isIt(),
                    unit.getCareer(), unit.getYearsText(), unit.getMinYears(), unit.getMaxYears(),
                    tree.itemsOf(unit).stream().map(item -> new UnitItemResponse(item.getId(), item.getCategory(),
                            item.getSeq(), item.getText(), item.getQuote(), tree.requirementsOf(item).stream()
                            .map(req -> new RequirementResponse(req.getId(), req.getCapability().getId(),
                                    req.getCapability().getName(), req.getOtherName(), req.getRelation(),
                                    tree.techsOf(req).stream().map(t -> new RequirementTechResponse(
                                            t.getTech() == null ? null : t.getTech().getId(),
                                            t.getTech() == null ? null : t.getTech().getName(), t.getWrittenName())).toList()))
                            .toList())).toList());
            return new UnitComparison(adapter.adapt(dto, tree.run().getSkipped()),
                    references.select(posting.getCompany().getId(), postingId, userId, byUnit.get(unit.getId())));
        }).toList();
        return new Response(postingId, userId, true, tree.run().hasRawOutput(), evidence, positions);
    }
}
