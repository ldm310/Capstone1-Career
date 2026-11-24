package com.career.backend.domain.posting;

import org.springframework.stereotype.Component;
import java.util.*;
import static com.career.backend.domain.posting.PostingDetailResponse.*;

/** Builds new DTOs only. Extraction entities and source JSON are never modified. */
@Component
public class PostingResultAdapter {
    // Names intentionally mirror the existing extractor contract, including other_name / it_job.
    public record Extraction(List<ExtractedPosition> positions, List<String> skipped, String notes) {}
    public record ExtractedPosition(String name, boolean it_job, String career, String years,
                                    List<Item> required, List<Item> preferred, List<Item> duties, List<Item> other) {}
    public record Item(String text, List<Req> reqs, String quote) {}
    public record Req(String capability, String other_name, List<String> techs, String relation) {}

    public List<Position> adapt(Extraction extraction, Map<String, Long> capabilityIds) {
        return safe(extraction.positions()).stream().map(p -> {
            List<UnitItemResponse> items = new ArrayList<>();
            append(items, "필수", p.required(), capabilityIds);
            append(items, "우대", p.preferred(), capabilityIds);
            append(items, "업무", p.duties(), capabilityIds);
            append(items, "기타", p.other(), capabilityIds);
            return adapt(new RecruitUnitResponse(null, null, p.name(), p.it_job(), p.career(), p.years(),
                    null, null, items), extraction.skipped());
        }).toList();
    }
    private static void append(List<UnitItemResponse> target, String category, List<Item> source, Map<String, Long> ids) {
        for (var item : safe(source)) target.add(new UnitItemResponse(null, category, null, item.text(), item.quote(),
                safe(item.reqs()).stream().map(r -> new RequirementResponse(null, ids.get(r.capability()),
                        r.capability(), r.other_name(), r.relation(), safe(r.techs()).stream()
                        .map(t -> new RequirementTechResponse(null, null, t)).toList())).toList()));
    }
    public record Skill(Long capabilityId, String capability, String otherName, List<String> techs,
                        String relation, String quote) {}
    public record Condition(RequiredConditionRules.Type type, String text, String quote) {}
    public record Position(Long unitId, String positionName, String career, String years,
                           List<Skill> requiredSkills, List<Condition> requiredConditions,
                           List<Skill> preferredSkills, List<Skill> dutySkills,
                           List<Skill> environmentSkills, List<String> skipped) {}

    public Position adapt(RecruitUnitResponse unit, List<String> skipped) {
        Set<Condition> conditions = new LinkedHashSet<>();
        Map<String, LinkedHashSet<Skill>> skills = new HashMap<>();
        for (UnitItemResponse item : safe(unit.items())) {
            if ("필수".equals(item.category())) {
                String text = Objects.requireNonNullElse(item.text(), "");
                var types = new LinkedHashSet<>(RequiredConditionRules.detect(text));
                types.addAll(RequiredConditionRules.detect(item.quote()));
                for (var type : types) conditions.add(new Condition(type, text, item.quote()));
            }
            for (RequirementResponse req : safe(item.requirements())) {
                String name = "기타".equals(req.capabilityName()) ? req.otherName() : req.capabilityName();
                // Classify the capability, not the whole sentence: mixed technical requirements survive.
                if (RequiredConditionRules.conditionCapability(name)) continue;
                List<String> techs = safe(req.techs()).stream()
                        .map(t -> t.techName() == null ? t.writtenName() : t.techName())
                        .filter(Objects::nonNull).filter(t -> !t.isBlank()).distinct().sorted().toList();
                skills.computeIfAbsent(item.category(), k -> new LinkedHashSet<>()).add(
                        new Skill(req.capabilityId(), req.capabilityName(), req.otherName(), techs, req.relation(), item.quote()));
            }
        }
        return new Position(unit.unitId(), unit.name(), unit.career(), unit.yearsText(),
                list(skills, "필수"), List.copyOf(conditions), list(skills, "우대"),
                list(skills, "업무"), list(skills, "기타"), List.copyOf(safe(skipped)));
    }
    private static List<Skill> list(Map<String, LinkedHashSet<Skill>> map, String key) {
        return List.copyOf(map.getOrDefault(key, new LinkedHashSet<>()));
    }
    private static <T> List<T> safe(List<T> list) { return list == null ? List.of() : list; }
}
