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
  source: "RDS";
  levels: SavedPostingLevel[];
  sources: {
    id: string;
    kind: "GITHUB" | "PDF";
    title: string;
    simulated: boolean;
  }[];
}
