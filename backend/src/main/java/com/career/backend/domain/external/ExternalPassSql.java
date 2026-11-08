package com.career.backend.domain.external;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import java.util.Map;

/** Fixed allowlist: pipeline identifiers and query parameters are never rewritten. */
public final class ExternalPassSql {
    private final NamedParameterJdbcTemplate jdbc;
    private static final Map<String,String> NAMES=Map.of(
            "pass_material","external_pass_material","company_collection","external_pass_company_collection",
            "posting_pass_material","external_pass_posting_material","collection_request","external_pass_collection_request",
            "collection_candidate","external_pass_collection_candidate");
    public ExternalPassSql(NamedParameterJdbcTemplate jdbc) { this.jdbc=jdbc; }
    public boolean publicOwned() {
        Integer count=jdbc.queryForObject("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('external_pass_material','external_pass_company_collection','external_pass_posting_material')",Map.of(),Integer.class);
        if(count!=null&&count!=0&&count!=3)throw new IllegalStateException("외부 합격자료 테이블 설치가 불완전합니다.");
        return count!=null&&count==3;
    }
    public String sql(String statement) {
        if(!publicOwned())return statement;
        for(var item:NAMES.entrySet())statement=statement.replace("external_data."+item.getKey(),"public."+item.getValue());
        return statement;
    }
    public void ensureCollectionInstalled() {
        boolean owned=publicOwned();
        Integer count=jdbc.queryForObject("""
                SELECT count(*) FROM information_schema.tables WHERE table_schema=:schema AND table_name IN (:names)
                """,Map.of("schema",owned?"public":"external_data","names",owned?NAMES.values():NAMES.keySet()),Integer.class);
        if(count==null||count!=5)throw new IllegalStateException("외부 합격자료 수집 스키마 적용이 필요합니다.");
    }
}
