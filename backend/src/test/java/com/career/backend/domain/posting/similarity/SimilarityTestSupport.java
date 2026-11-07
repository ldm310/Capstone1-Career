package com.career.backend.domain.posting.similarity;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;

final class SimilarityTestSupport {
    private SimilarityTestSupport() {}
    static Binder binder() {
        Properties properties=new Properties();
        try (var input=SimilarityTestSupport.class.getResourceAsStream("/posting-similarity.properties")) {
            Objects.requireNonNull(input);
            properties.load(new InputStreamReader(input,StandardCharsets.UTF_8));
        } catch (IOException e) { throw new UncheckedIOException(e); }
        Map<String,Object> values=new HashMap<>();
        properties.forEach((k,v) -> values.put(k.toString(),v));
        return new Binder(new MapConfigurationPropertySource(values));
    }
    static PostingSimilarityProperties properties() {
        return binder().bind("posting-similarity",Bindable.of(PostingSimilarityProperties.class)).orElseThrow(IllegalStateException::new);
    }
    static RecruitUnitRoleResolver resolver() {
        return new RecruitUnitRoleResolver(binder().bind("posting-similarity.taxonomy",Bindable.of(RoleTaxonomy.class)).orElseThrow(IllegalStateException::new));
    }
    static Set<Long> ids(long... values) {
        Set<Long> result=new HashSet<>(); for (long value : values) result.add(value); return result;
    }
    static IdSets sets(Set<Long> capabilities, Set<Long> techs) { return new IdSets(capabilities,techs); }
    static RecruitUnitFeatures unit(long posting, long company, long unit, String role, IdSets required) {
        return unit(posting,company,unit,role,null,null,required,IdSets.empty(),IdSets.empty());
    }
    static RecruitUnitFeatures unit(long posting, long company, long unit, String name, String category, String title,
                                    IdSets required, IdSets preferred, IdSets duties) {
        return new RecruitUnitFeatures(posting,company,posting*10,unit,name,category,title,
                Map.of(Category.REQUIRED,required,Category.PREFERRED,preferred,Category.DUTIES,duties));
    }
    static RecruitUnitFeatureRepository.Snapshot snapshot(RecruitUnitFeatures target, RecruitUnitFeatures... candidates) {
        List<RecruitUnitFeatures> units=new ArrayList<>(); units.add(target);units.addAll(List.of(candidates));
        Map<Long,Integer> counts=new HashMap<>(); units.forEach(u -> counts.put(u.postingId(),1));
        return new RecruitUnitFeatureRepository.Snapshot(target.postingId(),target.companyId(),counts,units);
    }
    static PostingCandidateSelectionService service(RecruitUnitFeatureRepository.Snapshot snapshot) {
        return service(snapshot,properties());
    }
    static PostingCandidateSelectionService service(RecruitUnitFeatureRepository.Snapshot snapshot, PostingSimilarityProperties p) {
        return new PostingCandidateSelectionService(id -> snapshot,resolver(),new KeywordPostingSimilarityScorer(),p);
    }
}
