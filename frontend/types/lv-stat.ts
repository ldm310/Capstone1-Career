// 스테이징 LV 서비스가 웹과 분석 작업자 사이에 주고받는 파일 형식(lv-stat/service/CONTRACT.md).

// 이 서비스가 재는 카테고리. 팀 코드 Q·S·H는 재지 않는다.
export type LvCategoryCode = "L" | "B" | "D" | "E" | "O" | "F" | "A";

export interface LvCategory {
  name: string;
  // 0.0~5.0(소수 첫째 자리). 그 카테고리의 변수가 모두 모름이면 null(판정 불가).
  lv: number | null;
  // 확인하지 못한 변수·항목 수('모름 n개').
  unknown: number;
}

export interface LvProgrammingCategory extends LvCategory {
  // GitHub Linguist 언어 이름 → 그 언어의 LV.
  languages: Record<string, number>;
  // 가장 높은 언어. 언어가 하나도 없으면 null.
  best: string | null;
}

// profiles/<profileKey>.json
export interface LvProfile {
  schema: "lv-stat-profile/1";
  method: string;
  labels: string[];
  namespace: string;
  subjectId: string;
  login: string;
  jobId: string;
  analyzedAt: string;
  repos: { found: number; analyzed: number; failed: number; notes: string[] };
  categories: Record<LvCategoryCode, LvCategory> & {
    L: LvProgrammingCategory;
  };
}

export type LvJobStatus = "queued" | "running" | "done" | "failed";
export type LvJobStage =
  | "대기"
  | "레포 찾기"
  | "레포 받기"
  | "색인"
  | "규칙 적용"
  | "계산"
  | "끝"
  | "실패";

// jobs/<jobId>.json. 웹이 queued로 만들고, 그 뒤로는 작업자만 고친다.
export interface LvJob {
  id: string;
  namespace: string;
  subjectId: string;
  login: string;
  input: string;
  status: LvJobStatus;
  createdAt: string;
  // 아래는 작업자가 더하는 칸이다.
  stage?: LvJobStage;
  progress?: { done: number; total: number } | null;
  startedAt?: string;
  finishedAt?: string;
  error?: string;
  profileKey?: string;
}
