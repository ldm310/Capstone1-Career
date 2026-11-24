package com.career.backend.domain.posting.similarity;

import org.springframework.stereotype.Component;
import java.text.Normalizer;
import java.util.*;
import java.util.regex.Pattern;

@Component
public class RecruitUnitRoleResolver {
    public enum Evidence { RECRUIT_UNIT_NAME, POSTING_CATEGORY, POSTING_TITLE, UNKNOWN }
    public enum Status { RESOLVED, UNKNOWN, AMBIGUOUS }
    public record RoleMatch(String roleCode, String familyCode, Status status, Evidence evidence,
                            List<String> matchedRoleCodes, String taxonomyVersion) {
        public RoleMatch { matchedRoleCodes=List.copyOf(matchedRoleCodes); }
        public boolean resolved() { return status==Status.RESOLVED; }
    }
    private record CompiledRule(String code, String family, Pattern pattern) {}
    private final String version;
    private final List<CompiledRule> rules;

    public RecruitUnitRoleResolver(RoleTaxonomy taxonomy) {
        version=Objects.requireNonNull(taxonomy.getVersion());
        Set<String> codes=new HashSet<>();
        rules=taxonomy.getRoles().stream().map(r -> {
            if (!codes.add(r.getCode())) throw new IllegalArgumentException("Duplicate role code");
            return new CompiledRule(r.getCode(),r.getFamily(),Pattern.compile(r.getPattern(),Pattern.CASE_INSENSITIVE|Pattern.UNICODE_CASE));
        }).toList();
        if (rules.isEmpty()) throw new IllegalArgumentException("Role rules are required");
    }

    public RoleMatch resolve(RecruitUnitFeatures unit) {
        RoleMatch match=match(unit.unitName(),Evidence.RECRUIT_UNIT_NAME);
        if (match!=null) return match; // Ambiguity is not resolved by broader posting metadata.
        match=match(unit.postingCategory(),Evidence.POSTING_CATEGORY);
        if (match!=null) return match;
        match=match(unit.postingTitle(),Evidence.POSTING_TITLE);
        return match!=null ? match : new RoleMatch(null,null,Status.UNKNOWN,Evidence.UNKNOWN,List.of(),version);
    }

    private RoleMatch match(String text, Evidence evidence) {
        if (text==null || text.isBlank()) return null;
        String normalized=Normalizer.normalize(text,Normalizer.Form.NFKC);
        var found=rules.stream().filter(r -> r.code().equalsIgnoreCase(normalized.strip()) || r.pattern().matcher(normalized).find())
                .sorted(Comparator.comparing(CompiledRule::code)).toList();
        if (found.isEmpty()) return null;
        if (found.size()>1) return new RoleMatch(null,null,Status.AMBIGUOUS,evidence,
                found.stream().map(CompiledRule::code).toList(),version);
        var rule=found.getFirst();
        return new RoleMatch(rule.code(),rule.family(),Status.RESOLVED,evidence,List.of(rule.code()),version);
    }
}
