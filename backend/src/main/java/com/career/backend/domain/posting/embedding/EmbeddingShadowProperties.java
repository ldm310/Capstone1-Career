package com.career.backend.domain.posting.embedding;

import jakarta.validation.constraints.*;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.PropertySource;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Component
@Validated
@PropertySource(value="classpath:embedding-shadow.properties",encoding="UTF-8")
@ConfigurationProperties("posting-embedding")
public class EmbeddingShadowProperties {
    public enum Mode { OFF, SHADOW_MODE }
    public static final String DEFAULT_MODEL="text-embedding-3-small";
    public static final String POLICY_VERSION="semantic-shadow-v1";
    @NotNull private Mode mode=Mode.SHADOW_MODE;
    @NotBlank private String model=DEFAULT_MODEL;
    @Min(1) @Max(3072) private int dimension=1536;
    @NotBlank private String modelRevision="embedding-config-v1";
    @NotBlank private String preprocessingVersion="requirement-input-v1";
    public Mode getMode(){return mode;} public void setMode(Mode v){mode=v;}
    public String getModel(){return model;} public void setModel(String v){model=v;}
    public int getDimension(){return dimension;} public void setDimension(int v){dimension=v;}
    public String getModelRevision(){return modelRevision;} public void setModelRevision(String v){modelRevision=v;}
    public String getPreprocessingVersion(){return preprocessingVersion;} public void setPreprocessingVersion(String v){preprocessingVersion=v;}
}
