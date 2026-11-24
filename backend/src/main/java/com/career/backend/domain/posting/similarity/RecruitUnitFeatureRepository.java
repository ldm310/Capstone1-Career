package com.career.backend.domain.posting.similarity;

import java.util.List;
import java.util.Map;

public interface RecruitUnitFeatureRepository {
    /** One SQL snapshot, including run counts before filtering IT units. */
    Snapshot load(long targetPostingId);

    record Snapshot(long targetPostingId, Long targetCompanyId, Map<Long, Integer> currentRunCounts,
                    List<RecruitUnitFeatures> units) {
        public Snapshot {
            currentRunCounts = Map.copyOf(currentRunCounts);
            units = List.copyOf(units);
        }
    }
}
