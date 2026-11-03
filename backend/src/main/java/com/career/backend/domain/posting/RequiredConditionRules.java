package com.career.backend.domain.posting;

import java.util.*;
import java.util.regex.Pattern;

/** All admission-condition detection rules live here; never classify programming languages as language tests. */
public final class RequiredConditionRules {
    public enum Type { CAREER_YEARS, EDUCATION, MAJOR, CERTIFICATE, LANGUAGE, EMPLOYMENT, OTHER }
    private static final Map<Type, Pattern> RULES = new LinkedHashMap<>();
    static {
        RULES.put(Type.CAREER_YEARS, Pattern.compile("(?:경력\\s*)?\\d+\\s*(?:[~～–-]\\s*\\d+\\s*)?년(?:\\s*(?:이상|이하|미만|초과))?"));
        RULES.put(Type.EDUCATION, Pattern.compile("학력|학사|석사|박사|대졸|초대졸|고졸|졸업|재학"));
        RULES.put(Type.MAJOR, Pattern.compile("전공|컴퓨터공학\\s*(?:과|계열)|관련\\s*학과"));
        RULES.put(Type.CERTIFICATE, Pattern.compile("자격증|자격\\s*보유|기사\\s*자격|정보처리기사"));
        RULES.put(Type.LANGUAGE, Pattern.compile("어학|토익|TOEIC|TOEFL|텝스|OPIc|영어\\s*(?:회화|능통|가능)|외국어|영어\\s*능력", Pattern.CASE_INSENSITIVE));
        RULES.put(Type.EMPLOYMENT, Pattern.compile("병역|군필|미필|전역|근무\\s*가능|출근\\s*가능|입사\\s*가능|취업\\s*가능|해외\\s*(?:여행|출장).*결격"));
    }
    private RequiredConditionRules() {}
    public static List<Type> detect(String text) {
        if (text == null) return List.of();
        return RULES.entrySet().stream().filter(e -> e.getValue().matcher(text).find()).map(Map.Entry::getKey).toList();
    }
    public static boolean conditionCapability(String name) {
        return name == null || name.isBlank() || !detect(name).isEmpty()
                || Set.of("경력", "경력 연수", "학위", "근무 가능 여부").contains(name);
    }
}
