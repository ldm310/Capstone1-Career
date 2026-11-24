package com.career.backend.domain.posting.similarity;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.AssertFalse;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.DecimalMax;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Component
@Validated
@ConfigurationProperties("posting-similarity")
public class PostingSimilarityProperties {
    @Min(1) private int maxCompanies;
    @Min(1) private int maxPostingsPerCompany;
    @Min(1) private int maxPostings;
    @NotBlank private String policyVersion;
    @DecimalMin("0.0") @DecimalMax("1.0") private double requiredCapabilityMinCoverage;
    @Min(1) private int requiredTechMinIntersection;
    @Min(2) private int minimumTotalEvidence;
    @Min(1) private int sparseRequiredSupportingEvidence;
    @Min(2) private int fallbackMinimumTargetFeatures;
    @Min(2) private int fallbackMinimumIntersection;
    @AssertFalse(message="An explicit role-pair allowlist is required before enabling expansion")
    private boolean jobFamilyExpansionEnabled;
    public int getMaxCompanies() { return maxCompanies; }
    public void setMaxCompanies(int value) { maxCompanies=value; }
    public int getMaxPostingsPerCompany() { return maxPostingsPerCompany; }
    public void setMaxPostingsPerCompany(int value) { maxPostingsPerCompany=value; }
    public int getMaxPostings() { return maxPostings; }
    public void setMaxPostings(int value) { maxPostings=value; }
    public String getPolicyVersion() { return policyVersion; }
    public void setPolicyVersion(String value) { policyVersion=value; }
    public double getRequiredCapabilityMinCoverage() { return requiredCapabilityMinCoverage; }
    public void setRequiredCapabilityMinCoverage(double value) { requiredCapabilityMinCoverage=value; }
    public int getRequiredTechMinIntersection() { return requiredTechMinIntersection; }
    public void setRequiredTechMinIntersection(int value) { requiredTechMinIntersection=value; }
    public int getMinimumTotalEvidence() { return minimumTotalEvidence; }
    public void setMinimumTotalEvidence(int value) { minimumTotalEvidence=value; }
    public int getSparseRequiredSupportingEvidence() { return sparseRequiredSupportingEvidence; }
    public void setSparseRequiredSupportingEvidence(int value) { sparseRequiredSupportingEvidence=value; }
    public int getFallbackMinimumTargetFeatures() { return fallbackMinimumTargetFeatures; }
    public void setFallbackMinimumTargetFeatures(int value) { fallbackMinimumTargetFeatures=value; }
    public int getFallbackMinimumIntersection() { return fallbackMinimumIntersection; }
    public void setFallbackMinimumIntersection(int value) { fallbackMinimumIntersection=value; }
    public boolean isJobFamilyExpansionEnabled() { return jobFamilyExpansionEnabled; }
    public void setJobFamilyExpansionEnabled(boolean value) { jobFamilyExpansionEnabled=value; }
}
