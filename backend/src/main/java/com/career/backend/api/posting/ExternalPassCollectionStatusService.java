package com.career.backend.api.posting;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import java.time.OffsetDateTime;
import java.util.*;
import static com.career.backend.api.posting.ExternalPassCollectionStatusRepository.*;

@Service
@Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ)
public class ExternalPassCollectionStatusService {
    private final ComparisonCandidatesQueryService selection;
    private final ExternalPassCollectionStatusRepository repository;
    private static final Set<String> SAFE_ERRORS=Set.of("ACCESS_RESTRICTED","FETCH_FAILED","HTML_LAYOUT_CHANGED",
            "SOURCE_COMPANY_CONFLICT","STALE_TASK","BE_CONTRACT_MISMATCH","COLLECTION_FAILED");
    public ExternalPassCollectionStatusService(ComparisonCandidatesQueryService selection,ExternalPassCollectionStatusRepository repository) {
        this.selection=selection;this.repository=repository;
    }
    public ExternalPassCollectionStatusResponse get(long postingId,long unitId) {
        var selected=selection.get(postingId,unitId); // Same 400/404/409 checks and unchanged Java similarity policy.
        repository.ensureInstalled();
        var direct=repository.directIds(postingId,selected.roleCode());
        if(!direct.isEmpty())return response(selected,"DIRECT",direct.size()>=5?"READY":"INSUFFICIENT",
                direct,List.of(),null,null,null,null);
        var request=repository.request(postingId,unitId,selected.policyVersion());
        List<Row> rows=request.map(r->repository.rows(r.id())).orElse(List.of());
        if(request.isPresent()) {
            if(!Objects.equals(request.get().roleCode(),selected.roleCode())||request.get().usedDirect())
                throw new IllegalStateException("수집 요청과 현재 비교 기준이 다릅니다. 배치에서 갱신해야 합니다.");
            var expected=new HashSet<>(selected.candidates().stream().map(ComparisonCandidatesResponse.Candidate::recruitUnitId).toList());
            var actual=new HashSet<>(rows.stream().map(Row::unitId).toList());
            if(!expected.equals(actual))throw new IllegalStateException("수집 요청의 후보가 현재 선정 결과와 다릅니다.");
        }
        Map<Long,Row> byUnit=new HashMap<>();rows.forEach(r->byUnit.put(r.unitId(),r));
        List<Row> current=new ArrayList<>();
        for(var c:selected.candidates()) {
            var row=byUnit.get(c.recruitUnitId());
            if(row!=null&&(row.postingId()!=c.postingId()||row.companyId()!=c.companyId()
                    ||!row.confidence().equals(c.confidence())||!Objects.equals(row.roleCode(),selected.roleCode())))
                throw new IllegalStateException("수집 요청의 후보 정보가 일치하지 않습니다.");
            current.add(row==null?new Row(c.recruitUnitId(),c.postingId(),c.companyId(),selected.roleCode(),c.confidence(),
                    false,false,null,null,null,null,null,Set.of()):row);
        }
        Set<Long> highIds=new HashSet<>();
        current.stream().filter(r->r.confidence().equals("HIGH")&&r.requested()).forEach(r->highIds.addAll(r.materialIds()));
        // Even if LOW was requested in an earlier batch, sufficient HIGH data takes precedence now.
        boolean highSettled=current.stream().filter(r->r.confidence().equals("HIGH"))
                .allMatch(r->r.requested()&&Set.of("READY","INSUFFICIENT","FAILED").contains(r.status()==null?"":r.status()));
        boolean useLow=highIds.size()<5&&highSettled;
        Set<Long> ids=new HashSet<>(highIds);
        if(useLow)current.stream().filter(r->r.confidence().equals("LOW")&&r.requested()).forEach(r->ids.addAll(r.materialIds()));
        var active=current.stream().filter(r->r.requested()&&(useLow||r.confidence().equals("HIGH"))).toList();
        String status;
        if(ids.size()>=5)status="READY";
        else if(active.stream().anyMatch(r->"RUNNING".equals(r.status())))status="RUNNING";
        else if(active.stream().anyMatch(r->r.status()==null||"PENDING".equals(r.status())))status="PENDING";
        else if(active.stream().anyMatch(r->"FAILED".equals(r.status())))status="FAILED";
        else if(!active.isEmpty()||!selected.selectionStatus().equals("SELECTED"))status="INSUFFICIENT";
        else status="NOT_REQUESTED";
        String error=active.stream().filter(r->"FAILED".equals(r.status())).map(Row::errorCode).filter(Objects::nonNull)
                .map(c->SAFE_ERRORS.contains(c)?c:"COLLECTION_FAILED").findFirst().orElse(null);
        boolean terminal=Set.of("READY","INSUFFICIENT","FAILED").contains(status);
        return response(selected,"CANDIDATES",status,ids,current,max(active.stream().map(Row::requestedAt).toList()),
                min(active.stream().map(Row::startedAt).toList()),terminal?max(active.stream().map(Row::completedAt).toList()):null,
                status.equals("FAILED")?error:null);
    }
    private ExternalPassCollectionStatusResponse response(ComparisonCandidatesResponse selected,String source,String status,
            Set<Long> ids,List<Row> rows,OffsetDateTime requested,OffsetDateTime started,OffsetDateTime completed,String error) {
        int high=(int)rows.stream().filter(r->r.confidence().equals("HIGH")).count();
        int companies=(int)rows.stream().filter(Row::requested).map(Row::companyId).distinct().count();
        int ready=(int)rows.stream().filter(r->r.requested()&&"READY".equals(r.status())).map(Row::companyId).distinct().count();
        var candidates=rows.stream().map(r->new ExternalPassCollectionStatusResponse.Candidate(r.companyId(),r.postingId(),r.unitId(),
                r.roleCode(),r.confidence(),r.requested()?(r.status()==null?"PENDING":r.status()):"NOT_REQUESTED",
                r.materialIds().size(),r.reused(),"EXACT_ROLE")).toList();
        String message=switch(status) {
            case "PENDING"->"합격자료 수집을 기다리고 있습니다.";
            case "RUNNING"->"합격자료를 분석하고 있습니다.";
            case "READY"->"합격자료 비교가 준비되었습니다.";
            case "FAILED"->"합격자료를 불러오지 못했습니다.";
            case "NOT_REQUESTED"->"합격자료 수집이 아직 요청되지 않았습니다.";
            default->selected.selectionStatus().equals("NO_CANDIDATES")?"비교할 유사 공고를 찾지 못했습니다.":
                    selected.selectionStatus().equals("NOT_COMPARABLE")?"현재 공고의 비교 기준이 부족합니다.":"비교 가능한 합격자료가 부족합니다.";
        };
        return new ExternalPassCollectionStatusResponse(selected.postingId(),selected.recruitUnitId(),selected.selectionStatus(),status,source,
                rows.size(),high,rows.size()-high,companies,ready,ids.size(),requested,started,completed,
                false,error,message,selected.policyVersion(),candidates);
    }
    private OffsetDateTime max(List<OffsetDateTime> dates) { return dates.stream().filter(Objects::nonNull).max(Comparator.naturalOrder()).orElse(null); }
    private OffsetDateTime min(List<OffsetDateTime> dates) { return dates.stream().filter(Objects::nonNull).min(Comparator.naturalOrder()).orElse(null); }
}
