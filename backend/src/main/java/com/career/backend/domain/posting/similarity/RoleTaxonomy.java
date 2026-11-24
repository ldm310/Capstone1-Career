package com.career.backend.domain.posting.similarity;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;
import java.util.*;

/** All role/family definitions live in posting-similarity.properties, not Java constants. */
@Component
@Validated
@ConfigurationProperties("posting-similarity.taxonomy")
public class RoleTaxonomy {
    @NotBlank private String version;
    @Valid @NotEmpty private List<Rule> roles = new ArrayList<>();
    public String getVersion() { return version; }
    public void setVersion(String value) { version=value; }
    public List<Rule> getRoles() { return roles; }
    public void setRoles(List<Rule> value) { roles=value; }
    public static class Rule {
        @NotBlank private String code;
        @NotBlank private String family;
        @NotBlank private String pattern;
        public String getCode() { return code; }
        public void setCode(String value) { code=value; }
        public String getFamily() { return family; }
        public void setFamily(String value) { family=value; }
        public String getPattern() { return pattern; }
        public void setPattern(String value) { pattern=value; }
    }
}
