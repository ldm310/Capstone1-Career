package com.career.backend.api.posting;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.*;

/** Read-only API enrichment. No body, external-material, queue or persistence operations. */
@Repository
public class ComparisonCandidateMetadataRepository {
    private final NamedParameterJdbcTemplate jdbc;
    public ComparisonCandidateMetadataRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc=jdbc; }

    public record TargetUnit(long recruitUnitId, long postingId, boolean current, boolean it) {}
    public record CandidateDetails(long postingId, long companyId, String companyName, String postingTitle,
                                   long recruitUnitId, String recruitUnitName) {}

    public boolean postingExists(long postingId) {
        return Objects.requireNonNull(jdbc.queryForObject("SELECT count(*) FROM public.posting WHERE id=:id",
                Map.of("id",postingId),Long.class))>0;
    }
    public Optional<TargetUnit> findUnit(long recruitUnitId) {
        return jdbc.query("""
                SELECT u.id,r.posting_id,r.is_current,u.is_it
                FROM public.recruit_unit u JOIN public.extraction_run r ON r.id=u.run_id WHERE u.id=:id
                """,Map.of("id",recruitUnitId),(rs,n)->new TargetUnit(rs.getLong(1),rs.getLong(2),rs.getBoolean(3),rs.getBoolean(4)))
                .stream().findFirst();
    }
    public Map<Long,CandidateDetails> findCandidateDetails(Collection<Long> recruitUnitIds) {
        if(recruitUnitIds.isEmpty())return Map.of();
        var rows=jdbc.query("""
                SELECT p.id,p.company_id,c.name,p.title,u.id AS unit_id,u.name AS unit_name
                FROM public.recruit_unit u JOIN public.extraction_run r ON r.id=u.run_id
                JOIN public.posting p ON p.id=r.posting_id JOIN public.company c ON c.id=p.company_id
                WHERE u.id IN (:ids) AND u.is_it=true AND r.is_current=true
                """,Map.of("ids",Set.copyOf(recruitUnitIds)),(rs,n)->new CandidateDetails(
                rs.getLong(1),rs.getLong(2),rs.getString(3),rs.getString(4),rs.getLong(5),rs.getString(6)));
        Map<Long,CandidateDetails> result=new HashMap<>();
        rows.forEach(row->result.put(row.recruitUnitId(),row));
        return Map.copyOf(result);
    }
}
