package com.career.backend.domain.posting.embedding;

import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

@Service
public class ShadowEmbeddingService {
    private final ShadowEmbeddingRepository repository;
    private final EmbeddingShadowProperties config;
    private final String taxonomyHash;
    public record UnitRef(long unitId,long runId,String roleCode) {}
    public ShadowEmbeddingService(ShadowEmbeddingRepository repository,EmbeddingShadowProperties config) {
        this.repository=repository;this.config=config;
        try {
            var text=new ClassPathResource("posting-similarity.properties").getContentAsString(StandardCharsets.UTF_8).replace("\r\n","\n");
            this.taxonomyHash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8)));
        }catch(Exception ex){throw new IllegalStateException("EMBEDDING_TAXONOMY_UNAVAILABLE");}
    }
    public Map<Long,EmbeddingShadowResult> score(UnitRef target,List<UnitRef> candidates) {
        if(config.getMode()==EmbeddingShadowProperties.Mode.OFF)return empty(candidates,"DISABLED");
        if(candidates.isEmpty())return Map.of();
        Set<Long> ids=new HashSet<>();ids.add(target.unitId());candidates.forEach(c->ids.add(c.unitId()));
        try {
            var snapshot=repository.load(ids,config);
            if(!snapshot.available())return empty(candidates,"NOT_GENERATED");
            Map<Long,List<ShadowEmbeddingRepository.Row>> rows=new HashMap<>();
            snapshot.rows().forEach(r->rows.computeIfAbsent(r.unitId(),k->new ArrayList<>()).add(r));
            var a=group(target,rows.getOrDefault(target.unitId(),List.of()));
            Map<Long,EmbeddingShadowResult> result=new HashMap<>();
            for(var candidate:candidates) {
                var b=group(candidate,rows.getOrDefault(candidate.unitId(),List.of()));
                Double[] scores=new Double[3];int count=0,index=0;
                for(String category:List.of("REQUIRED","PREFERRED","DUTIES")) {
                    var source=a.vectors.getOrDefault(category,List.of());var pool=b.vectors.getOrDefault(category,List.of());
                    if(!source.isEmpty()&&!pool.isEmpty()) {
                        double sum=0;
                        for(var vector:source)sum+=pool.stream().mapToDouble(v->CosineSimilarity.cosine(vector,v)).max().orElseThrow();
                        scores[index]=sum/source.size();count+=source.size();
                    }
                    index++;
                }
                String status=count>0?(a.missing||b.missing||a.stale||b.stale||a.error||b.error?"PARTIAL":"READY"):
                        a.stale||b.stale?"STALE":a.error||b.error?"UNAVAILABLE":"NOT_GENERATED";
                result.put(candidate.unitId(),new EmbeddingShadowResult(status,config.getModel(),EmbeddingShadowProperties.POLICY_VERSION,
                        scores[0],scores[1],scores[2],count));
            }
            return Map.copyOf(result);
        }catch(Exception ex){return empty(candidates,"UNAVAILABLE");}
    }
    private Map<Long,EmbeddingShadowResult> empty(List<UnitRef> candidates,String status) {
        Map<Long,EmbeddingShadowResult> result=new HashMap<>();
        candidates.forEach(c->result.put(c.unitId(),EmbeddingShadowResult.unavailable(status,config.getModel())));
        return Map.copyOf(result);
    }
    private static class Group {
        final Map<String,List<double[]>> vectors=new HashMap<>();boolean missing,stale,error;
    }
    private Group group(UnitRef expected,List<ShadowEmbeddingRepository.Row> rows) {
        Group result=new Group();
        for(var row:rows) {
            if(row.runId()!=expected.runId()){result.stale=true;continue;}
            if(row.storedFingerprint()==null){result.missing=true;continue;}
            if(!Objects.equals(row.fingerprint(),row.storedFingerprint())||!taxonomyHash.equals(row.taxonomyHash())) {
                result.stale=true;continue;
            }
            if("EXCLUDED".equals(row.eligibility()))continue;
            if(!Objects.equals(row.roleCode(),expected.roleCode())){result.stale=true;continue;}
            if(!"READY".equals(row.status())) {
                result.missing=true;result.error|=Set.of("FAILED","UNKNOWN").contains(Objects.toString(row.status(),""));continue;
            }
            if(!CosineSimilarity.valid(row.vector(),config.getDimension())){result.error=true;continue;}
            result.vectors.computeIfAbsent(row.category(),k->new ArrayList<>()).add(row.vector());
        }
        return result;
    }
}
