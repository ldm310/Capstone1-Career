package com.career.backend.domain.posting.similarity;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static com.career.backend.domain.posting.similarity.SimilarityTestSupport.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;

class KeywordPostingSimilarityScorerTest {
    private final PostingSimilarityScorer scorer=new KeywordPostingSimilarityScorer();

    @Test void coverageUsesTargetDenominatorAndSeparatesIdSpaces() {
        var target=unit(1,1,1,"backend",sets(ids(1,2),ids(1,3,4)));
        var other=unit(2,2,2,"backend",sets(ids(1,3),ids(2,3)));
        var score=scorer.score(target,other).category(Category.REQUIRED);
        assertEquals(ids(1),score.capability().intersectionIds());
        assertEquals(0.5,score.capability().coverage());
        assertEquals(ids(3),score.tech().intersectionIds());
        assertEquals(1.0/3,score.tech().coverage());
        assertEquals(2,score.tech().candidateCount());
    }
    @Test void emptyTargetAxesAreNotPerfectMatches() {
        var empty=unit(1,1,1,"backend",IdSets.empty());
        var score=scorer.score(empty,empty);
        for (var category : Category.values()) {
            assertNull(score.category(category).capability().coverage());
            assertFalse(score.category(category).tech().comparable());
        }
        assertFalse(score.hasRequiredOverlap());
    }
    @Test void nonemptyTargetAndEmptyCandidateIsZero() {
        var score=scorer.score(unit(1,1,1,"backend",sets(ids(1),ids(2))),
                unit(2,2,2,"backend",IdSets.empty()));
        assertEquals(0.0,score.category(Category.REQUIRED).capability().coverage());
        assertEquals(0.0,score.category(Category.REQUIRED).tech().coverage());
    }
    @Test void categoriesRetainSameTechnologyIndependentlyAndAreImmutable() {
        var shared=sets(Set.of(),ids(5,5,5));
        var target=unit(1,1,1,"backend",null,null,shared,shared,shared);
        var score=scorer.score(target,target);
        for (var category : Category.values()) {
            assertEquals(1,score.category(category).tech().targetCount());
            assertEquals(1,score.category(category).tech().intersectionCount());
            assertThrows(UnsupportedOperationException.class,() -> target.features(category).techIds().add(8L));
        }
    }
    @Test void preferredAndDutiesCannotReverseRequiredCapabilityOrder() {
        var both=sets(ids(1,2),ids(3,4));
        var target=unit(1,1,1,"backend",null,null,both,both,both);
        var stronger=unit(2,2,2,"backend",null,null,sets(ids(1,2),Set.of()),IdSets.empty(),IdSets.empty());
        var weaker=unit(3,3,3,"backend",null,null,sets(ids(1),ids(3,4)),both,both);
        assertTrue(PostingSimilarityScore.compareBestFirst(scorer.score(target,stronger),scorer.score(target,weaker))<0);
    }
    @Test void preferredAndDutiesCannotReverseRequiredTechOrder() {
        var both=sets(ids(1),ids(3,4));
        var target=unit(1,1,1,"backend",null,null,both,both,both);
        var stronger=unit(2,2,2,"backend",null,null,both,IdSets.empty(),IdSets.empty());
        var weaker=unit(3,3,3,"backend",null,null,sets(ids(1),ids(3)),both,both);
        assertTrue(PostingSimilarityScore.compareBestFirst(scorer.score(target,stronger),scorer.score(target,weaker))<0);
    }
    @Test void preferredBreaksRequiredTieBeforeDuties() {
        var ids=sets(ids(1),ids(2));
        var target=unit(1,1,1,"backend",null,null,ids,ids,ids);
        var preferred=unit(2,2,2,"backend",null,null,ids,ids,IdSets.empty());
        var duties=unit(3,3,3,"backend",null,null,ids,IdSets.empty(),ids);
        assertTrue(PostingSimilarityScore.compareBestFirst(scorer.score(target,preferred),scorer.score(target,duties))<0);
    }
    @Test void dutiesBreakRemainingTie() {
        var ids=sets(ids(1),ids(2));
        var target=unit(1,1,1,"backend",null,null,ids,IdSets.empty(),ids);
        var a=unit(2,2,2,"backend",null,null,ids,IdSets.empty(),ids);
        var b=unit(3,3,3,"backend",ids);
        assertTrue(PostingSimilarityScore.compareBestFirst(scorer.score(target,a),scorer.score(target,b))<0);
    }
    @Test void dtoSerializationIncludesCountsAndUncomparableFlag() {
        var score=scorer.score(unit(1,1,1,"backend",sets(ids(1),Set.of())),unit(2,2,2,"backend",sets(ids(1),Set.of())));
        var mapper=new tools.jackson.databind.ObjectMapper();
        var required=mapper.readTree(mapper.writeValueAsString(score)).get("categories").get("REQUIRED");
        assertEquals(1,required.get("capability").get("intersectionCount").asInt());
        assertTrue(required.get("capability").get("comparable").asBoolean());
        assertTrue(required.get("tech").get("coverage").isNull());
        assertFalse(required.get("tech").get("comparable").asBoolean());
    }
}
