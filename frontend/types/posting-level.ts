export interface SavedPostingLevel {
  keywordId: string;
  text: string;
  categoryCodes: string[];
  // LV_STAT만 준다: 점수를 낸 카테고리(scoreKeyword의 used). 재지 않는 코드(Q·S·H)와 LV가 없는(판정 불가)
  // 카테고리는 빠진다. categoryCodes는 화면이 문장과 맞추는 키라 문장 그대로 둔다.
  usedCodes?: string[];
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
