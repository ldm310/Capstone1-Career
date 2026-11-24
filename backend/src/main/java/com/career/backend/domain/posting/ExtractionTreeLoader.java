package com.career.backend.domain.posting;

import com.career.backend.domain.job.*;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

// 단계마다 IN 쿼리 한 번씩만 날려서 N+1 없이 트리를 만든다.
@Component
class ExtractionTreeLoader {

    private final ExtractionRunRepository extractionRunRepository;
    private final RecruitUnitRepository recruitUnitRepository;
    private final UnitItemRepository unitItemRepository;
    private final RequirementRepository requirementRepository;
    private final RequirementTechRepository requirementTechRepository;

    ExtractionTreeLoader(
            ExtractionRunRepository extractionRunRepository,
            RecruitUnitRepository recruitUnitRepository,
            UnitItemRepository unitItemRepository,
            RequirementRepository requirementRepository,
            RequirementTechRepository requirementTechRepository
    ) {
        this.extractionRunRepository = extractionRunRepository;
        this.recruitUnitRepository = recruitUnitRepository;
        this.unitItemRepository = unitItemRepository;
        this.requirementRepository = requirementRepository;
        this.requirementTechRepository = requirementTechRepository;
    }

    Optional<ExtractionTree> loadCurrent(Long postingId) {
        return extractionRunRepository.findByPostingIdAndCurrentTrue(postingId)
                .map(this::load);
    }

    private ExtractionTree load(ExtractionRun run) {
        List<RecruitUnit> units =
                recruitUnitRepository.findByRunIdOrderBySeq(run.getId());

        List<UnitItem> items = units.isEmpty()
                ? List.of()
                : unitItemRepository.findByUnitIdInOrderBySeq(
                        units.stream().map(RecruitUnit::getId).toList()
                );

        List<Requirement> requirements = items.isEmpty()
                ? List.of()
                : requirementRepository.findWithCapabilityByItemIdIn(
                        items.stream().map(UnitItem::getId).toList()
                );

        List<RequirementTech> techs = requirements.isEmpty()
                ? List.of()
                : requirementTechRepository.findWithTechByRequirementIdIn(
                        requirements.stream().map(Requirement::getId).toList()
                );

        return new ExtractionTree(
                run,
                units,
                groupBy(items, UnitItem::getUnitId),
                groupBy(requirements, Requirement::getItemId),
                groupBy(techs, RequirementTech::getRequirementId)
        );
    }

    private static <T> Map<Long, List<T>> groupBy(
            List<T> values,
            Function<T, Long> key
    ) {
        return values.stream().collect(Collectors.groupingBy(key));
    }
}
