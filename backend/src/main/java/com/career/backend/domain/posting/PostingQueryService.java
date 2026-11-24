package com.career.backend.domain.posting;

import com.career.backend.domain.common.NotFoundException;
import com.career.backend.domain.common.PageResponse;
import com.career.backend.domain.job.*;
import com.career.backend.domain.posting.PostingDetailResponse.*;
import com.career.backend.domain.posting.PostingFitResponse.CapabilityFitResponse;
import com.career.backend.domain.posting.PostingFitResponse.UnitFitResponse;
import com.career.backend.domain.profile.SkillLevel;
import com.career.backend.domain.profile.UserCapabilityService;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;

@Service
@Transactional(readOnly = true)
public class PostingQueryService {

    private static final Set<String> STATUSES = Set.of(Posting.OPEN, Posting.CLOSED);

    private final PostingRepository postingRepository;
    private final PostingImageRepository postingImageRepository;
    private final ExtractionTreeLoader extractionTreeLoader;
    private final UserCapabilityService userCapabilityService;

    public PostingQueryService(
            PostingRepository postingRepository,
            PostingImageRepository postingImageRepository,
            ExtractionTreeLoader extractionTreeLoader,
            UserCapabilityService userCapabilityService
    ) {
        this.postingRepository = postingRepository;
        this.postingImageRepository = postingImageRepository;
        this.extractionTreeLoader = extractionTreeLoader;
        this.userCapabilityService = userCapabilityService;
    }

    public PageResponse<PostingSummaryResponse> search(
            String keyword,
            String status,
            int page,
            int size
    ) {
        if (status != null && !STATUSES.contains(status)) {
            throw new IllegalArgumentException(
                    "status는 '진행' 또는 '마감'만 가능합니다."
            );
        }

        Specification<Posting> spec = (root, query, cb) -> cb.conjunction();

        if (status != null) {
            spec = spec.and((root, query, cb) ->
                    cb.equal(root.get("status"), status));
        }

        if (keyword != null && !keyword.isBlank()) {
            String pattern = "%" + keyword.trim().toLowerCase() + "%";
            spec = spec.and((root, query, cb) -> cb.or(
                    cb.like(cb.lower(root.get("title")), pattern),
                    cb.like(cb.lower(root.join("company").get("name")), pattern)
            ));
        }

        PageRequest pageRequest = PageRequest.of(
                page,
                size,
                Sort.by(Sort.Direction.DESC, "id")
        );

        return PageResponse.of(
                postingRepository.findAll(spec, pageRequest),
                PostingSummaryResponse::from
        );
    }

    public PostingDetailResponse getDetail(Long postingId) {
        Posting posting = findPosting(postingId);

        List<PostingImageResponse> images =
                postingImageRepository.findByPostingIdOrderBySeq(postingId)
                        .stream()
                        .map(image -> new PostingImageResponse(
                                image.getId(),
                                image.getSeq(),
                                image.getUrl(),
                                image.getKept()
                        ))
                        .toList();

        PostingAnalysisResponse analysis =
                extractionTreeLoader.loadCurrent(postingId)
                        .map(PostingQueryService::toAnalysis)
                        .orElse(null);

        return new PostingDetailResponse(
                posting.getId(),
                posting.getCompany().getName(),
                posting.getTitle(),
                posting.getSite(),
                posting.getSitePostingNo(),
                posting.getSiteJobCategory(),
                posting.getCareerCondition(),
                posting.getMinYears(),
                posting.getEmploymentType(),
                posting.getKind(),
                posting.getStatus(),
                posting.getDeadline(),
                posting.getCollectedAt(),
                posting.getLastCheckedAt(),
                images,
                analysis
        );
    }

    public PostingFitResponse getFit(Long postingId, Long userId) {
        Posting posting = findPosting(postingId);
        Map<Long, Integer> userScores =
                userCapabilityService.findBestScores(userId);

        Optional<ExtractionTree> tree =
                extractionTreeLoader.loadCurrent(postingId);

        List<UnitFitResponse> units = tree
                .map(t -> t.units().stream()
                        .filter(RecruitUnit::isIt)
                        .map(unit -> toUnitFit(t, unit, userScores))
                        .toList())
                .orElse(List.of());

        return new PostingFitResponse(
                posting.getId(),
                posting.getCompany().getName(),
                posting.getTitle(),
                userId,
                tree.isPresent(),
                units
        );
    }

    private Posting findPosting(Long postingId) {
        return postingRepository.findById(postingId)
                .orElseThrow(() ->
                        new NotFoundException("채용공고를 찾을 수 없습니다.")
                );
    }

    private static PostingAnalysisResponse toAnalysis(ExtractionTree tree) {
        List<RecruitUnitResponse> units = tree.units().stream()
                .map(unit -> new RecruitUnitResponse(
                        unit.getId(),
                        unit.getSeq(),
                        unit.getName(),
                        unit.isIt(),
                        unit.getCareer(),
                        unit.getYearsText(),
                        unit.getMinYears(),
                        unit.getMaxYears(),
                        tree.itemsOf(unit).stream()
                                .map(item -> toItem(tree, item))
                                .toList()
                ))
                .toList();

        return new PostingAnalysisResponse(
                tree.run().getId(),
                tree.run().getModel(),
                tree.run().getDictVersion(),
                tree.run().getRunAt(),
                units
        );
    }

    private static UnitItemResponse toItem(ExtractionTree tree, UnitItem item) {
        List<RequirementResponse> requirements = tree.requirementsOf(item)
                .stream()
                .map(requirement -> new RequirementResponse(
                        requirement.getId(),
                        requirement.getCapability().getId(),
                        requirement.getCapability().getName(),
                        requirement.getOtherName(),
                        requirement.getRelation(),
                        tree.techsOf(requirement).stream()
                                .map(tech -> new RequirementTechResponse(
                                        tech.getTech() == null ? null : tech.getTech().getId(),
                                        tech.getTech() == null ? null : tech.getTech().getName(),
                                        tech.getWrittenName()
                                ))
                                .toList()
                ))
                .toList();

        return new UnitItemResponse(
                item.getId(),
                item.getCategory(),
                item.getSeq(),
                item.getText(),
                item.getQuote(),
                requirements
        );
    }

    private static UnitFitResponse toUnitFit(
            ExtractionTree tree,
            RecruitUnit unit,
            Map<Long, Integer> userScores
    ) {
        return new UnitFitResponse(
                unit.getId(),
                unit.getName(),
                unit.getCareer(),
                unit.getYearsText(),
                collectFits(tree, unit, UnitItem.REQUIRED, userScores),
                collectFits(tree, unit, UnitItem.PREFERRED, userScores)
        );
    }

    // 같은 칸(필수/우대) 안에서 같은 능력은 하나로 묶고, 근거 문장과 기술을 모은다.
    private static List<CapabilityFitResponse> collectFits(
            ExtractionTree tree,
            RecruitUnit unit,
            String category,
            Map<Long, Integer> userScores
    ) {
        Map<String, FitBuilder> builders = new LinkedHashMap<>();

        for (UnitItem item : tree.itemsOf(unit)) {
            if (!category.equals(item.getCategory())) {
                continue;
            }

            for (Requirement requirement : tree.requirementsOf(item)) {
                String key = requirement.getCapability().getId()
                        + ":" + requirement.getOtherName();

                FitBuilder builder = builders.computeIfAbsent(
                        key,
                        ignored -> new FitBuilder(requirement)
                );

                builder.sourceTexts.add(item.getText());

                for (RequirementTech tech : tree.techsOf(requirement)) {
                    builder.techs.add(
                            tech.getTech() == null
                                    ? tech.getWrittenName()
                                    : tech.getTech().getName()
                    );
                }
            }
        }

        return builders.values().stream()
                .map(builder -> builder.build(userScores))
                .toList();
    }

    private static final class FitBuilder {

        private final Capability capability;
        private final String otherName;
        private final Set<String> techs = new LinkedHashSet<>();
        private final Set<String> sourceTexts = new LinkedHashSet<>();

        private FitBuilder(Requirement requirement) {
            this.capability = requirement.getCapability();
            this.otherName = requirement.getOtherName();
        }

        private CapabilityFitResponse build(Map<Long, Integer> userScores) {
            Integer score = userScores.get(capability.getId());

            return new CapabilityFitResponse(
                    capability.getId(),
                    capability.getName(),
                    otherName,
                    List.copyOf(techs),
                    List.copyOf(sourceTexts),
                    score != null,
                    score,
                    score == null ? null : SkillLevel.fromScore(score)
            );
        }
    }
}
