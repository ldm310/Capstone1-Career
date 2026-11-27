export interface SavedPostingLevel {
  keywordId: string;
  text: string;
  categoryCodes: string[];
  score: number;
  referenceScore: number | null;
  referenceKind:
    "SYNTHETIC_APPLICANTS" | "VERIFIED_APPLICANTS" | "REQUIREMENT" | null;
  evaluationKind: "DEMO" | "CONFIRMED";
  evaluatedAt: string;
}
export interface PostingLevels {
  jobId: string;
  taxonomyVersion: string;
  // RDS: 저장된 LV(career_lv_* 표). LV_STAT: 스테이징 LV 서비스의 분석 결과로 그 자리에서 계산한 LV.
  source: "RDS" | "LV_STAT";
  levels: SavedPostingLevel[];
  sources: {
    id: string;
    kind: "GITHUB" | "PDF";
    title: string;
    simulated: boolean;
  }[];
  // 아래는 LV_STAT만 준다. labels: 화면에 한 줄로 보일 결과 라벨, identityVerified: 본인 계정 확인 여부,
  // methodVersion: 계산 방식 판(결과 파일의 method).
  labels?: string[];
  identityVerified?: boolean;
  methodVersion?: string;
}
