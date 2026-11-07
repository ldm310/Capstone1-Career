package com.career.backend.domain.posting.similarity;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.*;
import static com.career.backend.domain.posting.similarity.RecruitUnitFeatures.*;

@Repository
public class JdbcRecruitUnitFeatureRepository implements RecruitUnitFeatureRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public JdbcRecruitUnitFeatureRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }

    // Counts are computed independently of unit/item joins. A broken one-current invariant
    // must be reported even when the offending run has no IT units or no requirements.
    private static final String SQL = """
            WITH target AS (SELECT id, company_id FROM public.posting WHERE id = :postingId),
            scope AS (
                SELECT p.id, p.company_id, p.title, p.site_job_category
                FROM public.posting p CROSS JOIN target t
                WHERE p.id=t.id OR p.company_id<>t.company_id
            ), run_counts AS (
                SELECT r.posting_id, count(*) AS current_count
                FROM public.extraction_run r JOIN scope s ON s.id=r.posting_id
                WHERE r.is_current=true GROUP BY r.posting_id
            )
            SELECT p.id AS posting_id, p.company_id, p.title, p.site_job_category,
                   coalesce(rc.current_count,0) AS current_count, r.id AS run_id,
                   u.id AS unit_id, u.name AS unit_name, i.category,
                   CASE WHEN c.is_active=true AND btrim(c.name)<>'기타' THEN c.id END AS capability_id,
                   CASE WHEN t.is_active=true THEN t.id END AS tech_id
            FROM scope p
            LEFT JOIN run_counts rc ON rc.posting_id=p.id
            LEFT JOIN public.extraction_run r ON r.posting_id=p.id AND r.is_current=true
            LEFT JOIN public.recruit_unit u ON u.run_id=r.id AND u.is_it=true
            LEFT JOIN public.unit_item i ON i.unit_id=u.id AND i.category IN ('필수','우대','업무')
            LEFT JOIN public.requirement q ON q.item_id=i.id
            LEFT JOIN public.capability c ON c.id=q.capability_id
            LEFT JOIN public.requirement_tech rt ON rt.requirement_id=q.id
            LEFT JOIN public.tech t ON t.id=rt.tech_id
            ORDER BY p.id,r.id,u.id,i.id,q.id,rt.id
            """;

    @Override
    public Snapshot load(long targetPostingId) {
        Map<Long, Integer> counts = new TreeMap<>();
        Map<Long, Builder> units = new LinkedHashMap<>();
        Long[] targetCompany = {null};
        jdbc.query(SQL, Map.of("postingId", targetPostingId), rs -> {
            long postingId = rs.getLong("posting_id");
            long companyId = rs.getLong("company_id");
            if (postingId == targetPostingId) targetCompany[0] = companyId;
            counts.put(postingId, rs.getInt("current_count"));
            Long unitId = rs.getObject("unit_id", Long.class);
            if (unitId == null) return;
            Builder builder = units.get(unitId);
            if (builder == null) {
                builder = new Builder(postingId, companyId, rs.getLong("run_id"), unitId,
                        rs.getString("unit_name"), rs.getString("site_job_category"), rs.getString("title"));
                units.put(unitId, builder);
            }
            Category category = switch (Objects.toString(rs.getString("category"), "")) {
                case "필수" -> Category.REQUIRED;
                case "우대" -> Category.PREFERRED;
                case "업무" -> Category.DUTIES;
                default -> null;
            };
            if (category == null) return;
            Long capabilityId = rs.getObject("capability_id", Long.class);
            Long techId = rs.getObject("tech_id", Long.class);
            if (capabilityId != null) builder.capabilities.get(category).add(capabilityId);
            if (techId != null) builder.techs.get(category).add(techId);
        });
        return new Snapshot(targetPostingId, targetCompany[0], counts,
                units.values().stream().map(Builder::build).toList());
    }

    private static final class Builder {
        final long postingId, companyId, runId, unitId;
        final String name, category, title;
        final Map<Category, Set<Long>> capabilities = new EnumMap<>(Category.class);
        final Map<Category, Set<Long>> techs = new EnumMap<>(Category.class);
        Builder(long postingId, long companyId, long runId, long unitId, String name, String category, String title) {
            this.postingId=postingId; this.companyId=companyId; this.runId=runId; this.unitId=unitId;
            this.name=name; this.category=category; this.title=title;
            for (var key : Category.values()) { capabilities.put(key,new HashSet<>()); techs.put(key,new HashSet<>()); }
        }
        RecruitUnitFeatures build() {
            Map<Category, IdSets> features = new EnumMap<>(Category.class);
            for (var key : Category.values()) features.put(key,new IdSets(capabilities.get(key),techs.get(key)));
            return new RecruitUnitFeatures(postingId,companyId,runId,unitId,name,category,title,features);
        }
    }
}
