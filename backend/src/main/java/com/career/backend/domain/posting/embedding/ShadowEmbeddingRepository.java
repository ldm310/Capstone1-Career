package com.career.backend.domain.posting.embedding;

import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.*;
import java.util.*;

@Repository
public class ShadowEmbeddingRepository {
    private final NamedParameterJdbcTemplate jdbc;
    public ShadowEmbeddingRepository(DataSource source) {
        var template=new JdbcTemplate(source);template.setQueryTimeout(1);
        this.jdbc=new NamedParameterJdbcTemplate(template);
    }
    public record Row(long requirementId,long unitId,long runId,String category,String fingerprint,
            String storedFingerprint,String taxonomyHash,String roleCode,String eligibility,String status,double[] vector) {}
    public record Snapshot(boolean available,List<Row> rows) { public Snapshot { rows=List.copyOf(rows); } }

    // Exceptions must be caught outside this proxy: a failed shadow query cannot abort the keyword transaction.
    @Transactional(readOnly=true,propagation=Propagation.REQUIRES_NEW,isolation=Isolation.REPEATABLE_READ,timeout=2)
    public Snapshot load(Set<Long> units,EmbeddingShadowProperties config) {
        Integer installed=jdbc.queryForObject("""
                SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN
                ('be_embedding_cache','be_requirement_embedding','be_embedding_source','be_requirement_embedding_view')
                """,Map.of(),Integer.class);
        if(installed==null||installed!=4)return new Snapshot(false,List.of());
        return new Snapshot(true,jdbc.query("""
                SELECT s.requirement_id,s.recruit_unit_id,s.source_run_id,s.category,s.source_fingerprint,
                    e.source_fingerprint AS stored_fingerprint,e.taxonomy_hash,e.role_code,e.eligibility,
                    e.embedding_status,e.embedding_text
                FROM public.be_embedding_source s LEFT JOIN public.be_requirement_embedding_view e
                    ON e.requirement_id=s.requirement_id AND e.model_name=:model AND e.model_revision=:revision
                    AND e.embedding_dimension=:dimension AND e.preprocessing_version=:preprocessing
                WHERE s.recruit_unit_id IN (:units) ORDER BY s.recruit_unit_id,s.requirement_id
                """,Map.of("units",units,"model",config.getModel(),"revision",config.getModelRevision(),
                        "dimension",config.getDimension(),"preprocessing",config.getPreprocessingVersion()),
                (rs,n)->new Row(rs.getLong("requirement_id"),rs.getLong("recruit_unit_id"),rs.getLong("source_run_id"),
                        rs.getString("category"),rs.getString("source_fingerprint"),rs.getString("stored_fingerprint"),
                        rs.getString("taxonomy_hash"),rs.getString("role_code"),rs.getString("eligibility"),
                        rs.getString("embedding_status"),parse(rs.getString("embedding_text")))));
    }

    static double[] parse(String value) {
        if(value==null)return null;
        if(value.length()<3)return new double[0];
        if(!((value.startsWith("{")&&value.endsWith("}"))||(value.startsWith("[")&&value.endsWith("]"))))return new double[0];
        try{return Arrays.stream(value.substring(1,value.length()-1).split(",")).mapToDouble(Double::parseDouble).toArray();}
        catch(NumberFormatException ex){return new double[0];}
    }
}
