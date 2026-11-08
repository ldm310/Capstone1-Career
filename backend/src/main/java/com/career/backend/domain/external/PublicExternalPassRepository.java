package com.career.backend.domain.external;

import com.career.backend.domain.common.PageResponse;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import java.time.OffsetDateTime;
import java.util.*;

@Repository
public class PublicExternalPassRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ExternalPassSql layout;
    public PublicExternalPassRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc=jdbc;this.layout=new ExternalPassSql(jdbc); }
    public boolean available() { return layout.publicOwned(); }
    public record Source(long id,String content) {}
    private static final String LINKS="""
            FROM public.external_pass_posting_material l JOIN public.posting p ON p.id=l.posting_id
            JOIN public.external_pass_material m ON m.id=l.material_id AND m.company_id=p.company_id
            WHERE p.id=:posting AND m.job_family='IT_SW' AND l.relation_type<>'EXCLUDED'
            """;
    public ExternalPassMaterialResponse.CollectionInfo collection(long companyId) {
        return jdbc.query("SELECT * FROM public.external_pass_company_collection WHERE company_id=:id",Map.of("id",companyId),
                (rs,n)->new ExternalPassMaterialResponse.CollectionInfo(companyId,CollectionStatus.valueOf(rs.getString("status")),
                        rs.getInt("minimum_sample_size"),rs.getInt("attempt_count"),rs.getObject("requested_at",OffsetDateTime.class),
                        rs.getObject("started_at",OffsetDateTime.class),rs.getObject("completed_at",OffsetDateTime.class),
                        rs.getObject("updated_at",OffsetDateTime.class),rs.getString("error_code"))).stream().findFirst().orElse(null);
    }
    public PageResponse<ExternalPassMaterialResponse.MaterialInfo> materials(long postingId,int page,int size) {
        var params=Map.of("posting",postingId,"limit",size,"offset",(long)page*size);
        Long count=jdbc.queryForObject("SELECT count(*) "+LINKS,params,Long.class);
        var rows=jdbc.query("SELECT m.*,l.relation_type "+LINKS+" ORDER BY m.collected_at DESC,m.id DESC LIMIT :limit OFFSET :offset",params,
                (rs,n)->new ExternalPassMaterialResponse.MaterialInfo(rs.getLong("id"),rs.getLong("company_id"),rs.getString("source_platform"),
                        rs.getString("external_record_id"),rs.getString("job_family"),rs.getString("role_name"),rs.getString("title"),
                        rs.getString("content"),rs.getString("source_url"),rs.getObject("published_at",OffsetDateTime.class),
                        rs.getObject("collected_at",OffsetDateTime.class),rs.getObject("updated_at",OffsetDateTime.class),
                        MaterialRelationType.valueOf(rs.getString("relation_type"))));
        long total=count==null?0:count;
        return new PageResponse<>(rows,page,size,total,(int)((total+size-1)/size));
    }
    public List<Source> keywordSources(long postingId) {
        return jdbc.query("SELECT DISTINCT m.id,m.content "+LINKS,Map.of("posting",postingId),
                (rs,n)->new Source(rs.getLong(1),rs.getString(2)));
    }
}
