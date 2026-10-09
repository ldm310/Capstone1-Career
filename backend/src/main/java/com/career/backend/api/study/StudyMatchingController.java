package com.career.backend.api.study;

import com.career.backend.domain.application.StudyMatchCandidate;
import com.career.backend.domain.application.StudyMatchingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/applications")
public class StudyMatchingController {

    private final StudyMatchingService studyMatchingService;

    public StudyMatchingController(
            StudyMatchingService studyMatchingService
    ) {
        this.studyMatchingService = studyMatchingService;
    }

    @GetMapping("/{applicationId}/study-matches")
    public List<StudyMatchCandidate> findStudyMatches(
            @PathVariable Long applicationId
    ) {
        return studyMatchingService.findCandidates(applicationId);
    }
}