package com.career.backend.domain.external;

import com.career.backend.domain.common.NotFoundException;
import com.career.backend.domain.job.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.util.*;
import static com.career.backend.domain.external.ExternalPassKeywordResponse.KeywordCount;

@Service
@Transactional(readOnly = true)
public class ExternalPassKeywordService {
    private final PostingRepository postings;
    private final ExternalPassMaterialRepository materials;
    private final TechRepository techs;
    private final RequirementTechRepository requirements;
    private final ObjectMapper json;
    private final PublicExternalPassRepository publicStore;

    public ExternalPassKeywordService(PostingRepository postings, ExternalPassMaterialRepository materials,
            TechRepository techs, RequirementTechRepository requirements, ObjectMapper json,PublicExternalPassRepository publicStore) {
        this.postings = postings; this.materials = materials; this.techs = techs;
        this.requirements = requirements; this.json = json;
        this.publicStore=publicStore;
    }

    public ExternalPassKeywordResponse get(Long postingId) {
        if (!postings.existsById(postingId)) throw new NotFoundException("채용공고를 찾을 수 없습니다.");
        // One material is one source, regardless of repeated keywords or requirement links.
        Map<Long, PublicExternalPassRepository.Source> sources = new LinkedHashMap<>();
        if(publicStore.available())publicStore.keywordSources(postingId).forEach(m->sources.putIfAbsent(m.id(),m));
        else materials.findAllLinkedForKeywords(postingId).forEach(m -> sources.putIfAbsent(m.getId(),
                new PublicExternalPassRepository.Source(m.getId(),m.getContent())));
        if (sources.isEmpty()) return new ExternalPassKeywordResponse(postingId, 0,
                List.of(), List.of(), List.of(), List.of());

        var mapper = new TechKeywordMapper(techs.findAll().stream()
                .map(t -> new TechKeywordMapper.Entry(t.getId(), t.getName(), t.getAliases())).toList());
        Set<Long> required = new HashSet<>(), preferred = new HashSet<>();
        for (var requirement : requirements.findCurrentPostingTechs(postingId)) {
            if (UnitItem.REQUIRED.equals(requirement.getCategory())) required.add(requirement.getTechId());
            if (UnitItem.PREFERRED.equals(requirement.getCategory())) preferred.add(requirement.getTechId());
        }
        preferred.removeAll(required);

        Map<Long, Integer> counts = new TreeMap<>();
        Map<String, String> unmapped = new TreeMap<>();
        for (var material : sources.values()) {
            Set<Long> materialTechs = new HashSet<>();
            for (String keyword : keywords(material.content())) {
                var matched = mapper.match(keyword);
                if (matched.isPresent()) materialTechs.add(matched.get().id());
                else unmapped.merge(TechKeywordMapper.normalize(keyword), keyword,
                        (a, b) -> a.compareTo(b) <= 0 ? a : b);
            }
            materialTechs.forEach(id -> counts.merge(id, 1, Integer::sum));
        }

        List<KeywordCount> requiredOverlap = new ArrayList<>(), preferredOverlap = new ArrayList<>(), externalOnly = new ArrayList<>();
        counts.forEach((id, count) -> {
            var value = new KeywordCount(id, mapper.get(id).name(), count);
            if (required.contains(id)) requiredOverlap.add(value);
            else if (preferred.contains(id)) preferredOverlap.add(value);
            else externalOnly.add(value);
        });
        return new ExternalPassKeywordResponse(postingId, sources.size(), List.copyOf(requiredOverlap),
                List.copyOf(preferredOverlap), List.copyOf(externalOnly), List.copyOf(unmapped.values()));
    }

    private List<String> keywords(String content) {
        if (content == null) return List.of();
        try {
            Object root = json.readValue(content, Object.class);
            if (!(root instanceof Map<?, ?> fields) || !(fields.get("technologies") instanceof List<?> values)) {
                return List.of();
            }
            return values.stream().filter(String.class::isInstance).map(String.class::cast)
                    .map(String::strip).filter(s -> !s.isEmpty()).toList();
        } catch (JacksonException exception) {
            // Legacy plain-text or malformed content must not be re-tokenized or exposed as keywords.
            return List.of();
        }
    }
}
