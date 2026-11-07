package com.career.backend.domain.posting.similarity;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import static org.junit.jupiter.api.Assertions.*;
import static com.career.backend.domain.posting.similarity.SimilarityTestSupport.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.IdSets;
import static com.career.backend.domain.posting.similarity.RecruitUnitRoleResolver.*;

class RecruitUnitRoleResolverTest {
    private final RecruitUnitRoleResolver resolver=resolver();
    @ParameterizedTest
    @CsvSource({"백엔드 개발자,backend,software", "서버 개발자,backend,software", "프론트엔드 개발자,frontend,software",
            "풀스택,fullstack,software", "iOS 개발자,mobile,software", "임베디드,embedded,software",
            "QA 엔지니어,qa,software", "소프트웨어 개발자,software,software", "데이터 엔지니어,data_engineer,data",
            "데이터 분석가,data_scientist,data", "AI 엔지니어,ml_engineer,data", "ML 엔지니어,ml_engineer,data",
            "머신러닝 엔지니어,ml_engineer,data", "Machine Learning Engineer,ml_engineer,data", "SRE,devops,infrastructure",
            "정보보안,security,infrastructure"})
    void mappingComesFromProductionResource(String name,String code,String family) {
        var match=resolver.resolve(unit(1,1,1,name,IdSets.empty()));
        assertEquals(code,match.roleCode());assertEquals(family,match.familyCode());
        assertEquals(Evidence.RECRUIT_UNIT_NAME,match.evidence());
    }
    @Test void unitNameOverridesContradictingPostingMetadata() {
        var u=unit(1,1,1,"프론트엔드","백엔드","데이터 엔지니어",IdSets.empty(),IdSets.empty(),IdSets.empty());
        var role=resolver.resolve(u);
        assertEquals("frontend",role.roleCode());assertEquals(Evidence.RECRUIT_UNIT_NAME,role.evidence());
    }
    @Test void categoryIsUsedOnlyWhenNameCannotResolve() {
        var u=unit(1,1,1,"플랫폼팀","백엔드","프론트엔드",IdSets.empty(),IdSets.empty(),IdSets.empty());
        var role=resolver.resolve(u);
        assertEquals("backend",role.roleCode());assertEquals(Evidence.POSTING_CATEGORY,role.evidence());
    }
    @Test void titleIsLastFallback() {
        var u=unit(1,1,1,"플랫폼팀","개발","서버 개발자 채용",IdSets.empty(),IdSets.empty(),IdSets.empty());
        assertEquals(Evidence.POSTING_TITLE,resolver.resolve(u).evidence());
    }
    @Test void ambiguousNameIsNotReplacedByMetadata() {
        var u=unit(1,1,1,"백엔드 / 프론트엔드","백엔드","백엔드",IdSets.empty(),IdSets.empty(),IdSets.empty());
        var role=resolver.resolve(u);
        assertEquals(Status.AMBIGUOUS,role.status());assertNull(role.roleCode());
        assertEquals(Evidence.RECRUIT_UNIT_NAME,role.evidence());assertEquals(2,role.matchedRoleCodes().size());
    }
    @Test void ambiguousCategoryDoesNotFallThroughToTitle() {
        var u=unit(1,1,1,"플랫폼팀","백엔드 / 프론트엔드","백엔드",IdSets.empty(),IdSets.empty(),IdSets.empty());
        assertEquals(Status.AMBIGUOUS,resolver.resolve(u).status());
        assertEquals(Evidence.POSTING_CATEGORY,resolver.resolve(u).evidence());
    }
    @Test void unknownIsExplicit() {
        var role=resolver.resolve(unit(1,1,1,"알 수 없는 직무",IdSets.empty()));
        assertEquals(Status.UNKNOWN,role.status());assertEquals(Evidence.UNKNOWN,role.evidence());
    }
    @Test void canonicalCodesAreAlsoRecognizedWithoutDuplicatingMapping() {
        var taxonomy=binder().bind("posting-similarity.taxonomy",org.springframework.boot.context.properties.bind.Bindable.of(RoleTaxonomy.class))
                .orElseThrow(IllegalStateException::new);
        for (var rule : taxonomy.getRoles()) {
            var match=resolver.resolve(unit(1,1,1,rule.getCode(),IdSets.empty()));
            assertEquals(rule.getCode(),match.roleCode());assertEquals(rule.getFamily(),match.familyCode());
        }
    }
    @Test void concreteMlNameOverridesDataCategoryButConflictRemainsAmbiguous() {
        var u=unit(1,1,1,"ML 엔지니어","데이터 엔지니어","Backend",IdSets.empty(),IdSets.empty(),IdSets.empty());
        assertEquals("ml_engineer",resolver.resolve(u).roleCode());
        assertEquals(Evidence.RECRUIT_UNIT_NAME,resolver.resolve(u).evidence());
        var conflict=unit(1,1,1,"ML 엔지니어 / 백엔드 개발자","데이터 엔지니어","Backend",IdSets.empty(),IdSets.empty(),IdSets.empty());
        assertEquals(Status.AMBIGUOUS,resolver.resolve(conflict).status());
    }
    @Test void invalidAndDuplicateRoleConfigurationFailsEarly() {
        var taxonomy=binder().bind("posting-similarity.taxonomy",org.springframework.boot.context.properties.bind.Bindable.of(RoleTaxonomy.class))
                .orElseThrow(IllegalStateException::new);
        taxonomy.getRoles().add(taxonomy.getRoles().getFirst());
        assertThrows(IllegalArgumentException.class,() -> new RecruitUnitRoleResolver(taxonomy));
        taxonomy.getRoles().removeLast();taxonomy.getRoles().getFirst().setPattern("[");
        assertThrows(java.util.regex.PatternSyntaxException.class,() -> new RecruitUnitRoleResolver(taxonomy));
    }
}
