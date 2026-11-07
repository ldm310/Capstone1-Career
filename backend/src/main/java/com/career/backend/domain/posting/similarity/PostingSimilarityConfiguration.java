package com.career.backend.domain.posting.similarity;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

/** Feature defaults also load when a test supplies its own application.properties. */
@Configuration(proxyBeanMethods=false)
@PropertySource(value="classpath:posting-similarity.properties",encoding="UTF-8")
public class PostingSimilarityConfiguration {}
