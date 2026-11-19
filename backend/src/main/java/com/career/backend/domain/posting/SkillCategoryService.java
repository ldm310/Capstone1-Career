package com.career.backend.domain.posting;

import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.HexFormat;
import java.util.List;
import java.util.regex.Pattern;

/** Read-only saved classifications. No model calls, dictionary writes or LV calculation. */
@Service
public class SkillCategoryService {
    private static final Pattern SPACE = Pattern.compile("\\s+", Pattern.UNICODE_CHARACTER_CLASS);
    private final ObjectMapper mapper;
    private final Catalog catalog;
    private final JsonNode entries;

    public SkillCategoryService(ObjectMapper mapper) throws IOException {
        this.mapper = mapper;
        try (var input = new ClassPathResource("skill-categories/reviewed-20261119.json").getInputStream()) {
            var snapshot = mapper.readTree(input);
            catalog = mapper.treeToValue(snapshot.get("catalog"), Catalog.class);
            entries = snapshot.get("entries");
        }
    }

    public record Category(String code, String name, int sentenceCount) {}
    public record RelatedGroup(String id, String label, String kind, int count) {}
    public record Catalog(String version, String reviewedAt, String scope, String sourceSha256,
                          int totalSentences, int countedSentences, int excludedSentences,
                          int unclassifiedSentences, int otherSentences, boolean categoriesOverlap,
                          boolean levelScoringEnabled, List<Category> categories, List<Category> auxiliaryTags,
                          List<RelatedGroup> otherGroups, boolean otherGroupsOverlap,
                          int certificateReferenceSentences) {}

    public Catalog catalog() { return catalog; }

    public record Assignment(String status, List<String> categoryCodes, boolean excludedFromCounts,
                             boolean needsReview, List<String> relatedGroups) {}
    public record Item(Long itemId, String sourceCategory, String text, Assignment assignment) {}
    public record Unit(Long unitId, String name, List<Item> items) {}
    public record PostingCategories(Long postingId, String version, String analysisStatus, List<Unit> recruitUnits) {}

    public Assignment classify(String text) {
        var row = text == null ? null : entries.get(fingerprint(text));
        if (row == null) return new Assignment("UNCLASSIFIED", List.of(), false, false, List.of());
        boolean excluded = row.path("excluded").asBoolean();
        return new Assignment(excluded ? "EXCLUDED" : "CLASSIFIED",
                strings(row.get("categoryCodes")), excluded, row.path("needsReview").asBoolean(),
                strings(row.get("relatedGroups")));
    }

    public PostingCategories forPosting(PostingDetailResponse posting) {
        var analysis = posting.analysis();
        var units = analysis == null ? List.<Unit>of() : analysis.recruitUnits().stream().map(unit ->
                new Unit(unit.unitId(), unit.name(), unit.items().stream().map(item -> new Item(
                        item.itemId(), item.category(), item.text(),
                        "필수".equals(item.category()) || "우대".equals(item.category()) ? classify(item.text()) :
                                new Assignment("NOT_APPLICABLE", List.of(), false, false, List.of())
                )).toList())).toList();
        return new PostingCategories(posting.postingId(), catalog.version(),
                analysis == null ? "NOT_ANALYZED" : "ANALYZED", units);
    }

    private List<String> strings(JsonNode value) {
        return mapper.convertValue(value, mapper.getTypeFactory().constructCollectionType(List.class, String.class));
    }

    static String fingerprint(String text) {
        var normalized = SPACE.matcher(Normalizer.normalize(text, Normalizer.Form.NFC)).replaceAll(" ").trim();
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(normalized.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
