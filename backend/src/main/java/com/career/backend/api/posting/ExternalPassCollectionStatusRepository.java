package com.career.backend.api.posting;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import com.career.backend.domain.external.ExternalPassSql;
import java.time.OffsetDateTime;
import java.util.*;

@Repository
public class ExternalPassCollectionStatusRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ExternalPassSql layout;
    public ExternalPassCollectionStatusRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc=jdbc;this.layout=new ExternalPassSql(jdbc); }
    public record Request(long id,String roleCode,boolean usedDirect) {}
    public record Row(long unitId,long postingId,long companyId,String roleCode,String confidence,
            boolean requested,boolean reused,String status,String errorCode,
            OffsetDateTime requestedAt,OffsetDateTime startedAt,OffsetDateTime completedAt,Set<Long> materialIds) {}

    public void ensureInstalled() {
        layout.ensureCollectionInstalled();
    }
    public Set<Long> directIds(long postingId,String roleCode) {
        if(roleCode==null)return Set.of();
        return Set.copyOf(jdbc.queryForList(layout.sql("""
                SELECT DISTINCT m.id FROM external_data.posting_pass_material l
                JOIN public.posting p ON p.id=l.posting_id JOIN external_data.pass_material m ON m.id=l.material_id
                WHERE p.id=:posting AND p.company_id=m.company_id AND m.job_family='IT_SW'
                  AND l.relation_type<>'EXCLUDED' AND m.role_name=:role
                """),Map.of("posting",postingId,"role",roleCode),Long.class));
    }
    public Optional<Request> request(long postingId,long unitId,String version) {
        return jdbc.query(layout.sql("""
                SELECT id,standard_role_code,used_direct FROM external_data.collection_request
                WHERE target_posting_id=:posting AND target_recruit_unit_id=:unit AND policy_version=:version
                """),Map.of("posting",postingId,"unit",unitId,"version",version),
                (rs,n)->new Request(rs.getLong(1),rs.getString(2),rs.getBoolean(3))).stream().findFirst();
    }
    public List<Row> rows(long requestId) {
        var params=Map.of("request",requestId);
        Map<Long,Set<Long>> materials=new HashMap<>();
        jdbc.query(layout.sql("""
                SELECT c.candidate_recruit_unit_id,m.id FROM external_data.collection_candidate c
                JOIN public.posting p ON p.id=c.candidate_posting_id AND p.company_id=c.candidate_company_id
                JOIN external_data.posting_pass_material l ON l.posting_id=p.id AND l.relation_type='EXACT_ROLE'
                JOIN external_data.pass_material m ON m.id=l.material_id AND m.company_id=p.company_id
                  AND m.job_family='IT_SW' AND m.role_name=c.standard_role_code
                WHERE c.request_id=:request AND c.is_selected=true AND c.requested=true
                """),params,rs->{materials.computeIfAbsent(rs.getLong(1),k->new HashSet<>()).add(rs.getLong(2));});
        return jdbc.query(layout.sql("""
                SELECT c.candidate_recruit_unit_id,c.candidate_posting_id,c.candidate_company_id,
                  c.standard_role_code,c.confidence,c.requested,c.reused,t.status,t.error_code,
                  c.requested_at,t.started_at,t.completed_at
                FROM external_data.collection_candidate c LEFT JOIN external_data.company_collection t
                  ON t.company_id=c.candidate_company_id
                WHERE c.request_id=:request AND c.is_selected=true ORDER BY c.candidate_rank,c.id
                """),params,(rs,n)->new Row(rs.getLong(1),rs.getLong(2),rs.getLong(3),rs.getString(4),rs.getString(5),
                        rs.getBoolean(6),rs.getBoolean(7),rs.getString(8),rs.getString(9),
                        rs.getObject(10,OffsetDateTime.class),rs.getObject(11,OffsetDateTime.class),
                        rs.getObject(12,OffsetDateTime.class),Set.copyOf(materials.getOrDefault(rs.getLong(1),Set.of()))));
    }
}
